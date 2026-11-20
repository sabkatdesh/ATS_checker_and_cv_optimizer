"""Cancel checkpoints around every node, progress hooks, and the cancelled session status."""

import threading
import time
from pathlib import Path

import pytest

from app.adapters.background.inline_runner import InlineRunner
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm.fake import DEFAULT_DIR, FakeTransport
from app.adapters.llm.fake import Hang as FakeHang
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.usage.memory_sink import MemoryUsageSink
from app.config.llm_routes import load_route_table
from app.config.settings import AppSettings
from app.container import Container
from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.domain.trust.judge import JudgeFindings
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.deps import PipelineDeps
from app.pipeline.errors import PipelineCancelled
from app.pipeline.graph import build_graph
from app.pipeline.hooks import NODE_STAGES, ProgressEvent
from app.pipeline.prompts.loader import PromptLibrary
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from app.services.generation import resume_after_answers, run_new_session
from tests.fakes.backend import backend_with_session, legacy_status_of
from tests.fakes.fake_auth import USER_A
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.pipeline.helpers import deps_for, persona_cv, persona_jd_text, persona_profile, tech_jd
from tests.pipeline.scripted_gateway import Hang, Outcome, ScriptedGateway

TID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a02"
PERSONA = Path(__file__).resolve().parents[2] / "fixtures" / "personas" / "tech_backend"
OPTIONS = RunOptions(cover_letter=True, cover_letter_tone="formal", cover_letter_length="short")
# Node runs on the happy path, with questions answered and a cover letter requested.
SEQUENCE = [
    "jd_extract",
    "cv_snapshot",
    "eligibility",
    "gap_questions",
    "await_answers",
    "ats_score",
    "rewrite",
    "ats_score",
    "verify_claims",
    "cover_letter_options",
    "cover_letter",
]
PAIRS = [(i, SEQUENCE[i], SEQUENCE[i + 1]) for i in range(len(SEQUENCE) - 1)]


def _draft() -> RewrittenCV:
    draft = RewrittenCV.model_validate_json((DEFAULT_DIR / "rewrite.json").read_text("utf-8"))
    return draft.model_copy(update={"meta": persona_cv().meta, "education": persona_cv().education})


def _script(**extra: list[Outcome]) -> dict[str, list[Outcome]]:
    letter = CoverLetterStructured.model_validate_json(
        (DEFAULT_DIR / "cover_letter.json").read_text("utf-8")
    )
    return {
        "jd_extract": [tech_jd()],
        "eligibility": [Eligibility(score=60, gaps=["Kubernetes"])],
        "gap_questions": [GapQuestions(questions=[GapQuestion(id="q1", text="Kubernetes?")])],
        "rewrite": [_draft(), _draft()],
        "verify_claims": [JudgeFindings()],
        "cover_letter": [letter],
        **extra,
    }


class Recorder:
    """Records progress events; cancels the run when finished event number `cancel_at` arrives."""

    def __init__(self, svc: PipelineService, gw: ScriptedGateway, cancel_at: int = -1) -> None:
        self.svc, self.gw, self.cancel_at = svc, gw, cancel_at
        self.events: list[ProgressEvent] = []
        self.finished = 0
        self.requests_at_cancel: int | None = None

    async def before_node(self, event: ProgressEvent) -> None:
        self.events.append(event)

    async def after_node(self, event: ProgressEvent) -> None:
        self.events.append(event)
        if self.finished == self.cancel_at:
            self.requests_at_cancel = len(self.gw.requests)
            assert self.svc.cancel(TID) is True
        self.finished += 1


def _service(script: dict[str, list[Outcome]]) -> tuple[ScriptedGateway, PipelineService]:
    gw, deps = deps_for(script)
    return gw, PipelineService(build_graph(deps, new_checkpointer()), deps.runs)


def _start(svc: PipelineService, hooks: object = None) -> None:
    svc.run(
        job_description=persona_jd_text(),
        profile=persona_profile(),
        thread_id=TID,
        options=OPTIONS,
        hooks=hooks,  # type: ignore[arg-type]
    )


def _run_all(svc: PipelineService, hooks: object) -> dict:
    _start(svc, hooks)
    assert svc.get_state(TID)["next"] == ["await_answers"]
    return svc.resume(TID, "I run Kubernetes clusters", hooks=hooks)  # type: ignore[arg-type]


def test_happy_path_node_sequence():
    gw, svc = _service(_script())
    hooks = Recorder(svc, gw)
    final = _run_all(svc, hooks)
    assert final["cover_letter"] is not None
    assert [e.node for e in hooks.events if e.phase == "finished"] == SEQUENCE
    assert svc.cancel(TID) is False  # the run context is closed when the run ends


@pytest.mark.parametrize(("index", "a", "b"), PAIRS, ids=[f"{a}->{b}" for _, a, b in PAIRS])
def test_cancel_between_nodes(index: int, a: str, b: str):
    gw, svc = _service(_script())
    hooks = Recorder(svc, gw, cancel_at=index)
    with pytest.raises(PipelineCancelled) as info:
        _run_all(svc, hooks)
    assert (info.value.node, info.value.when) == (a, "after")
    assert info.value.stage == NODE_STAGES[a][0]
    last = hooks.events[-1]
    assert (last.node, last.phase) == (a, "finished")  # before_node(b) never ran
    assert len(gw.requests) == hooks.requests_at_cancel
    summary = svc.summary(TID)
    assert summary is not None and summary.cancelled_stage == NODE_STAGES[a][0]


def test_cancel_while_paused_blocks_resume():
    gw, svc = _service(_script())
    _start(svc)
    sent = len(gw.requests)
    assert svc.cancel(TID) is True
    with pytest.raises(PipelineCancelled) as info:
        svc.resume(TID, "answers")
    assert (info.value.node, info.value.when) == ("await_answers", "before")
    assert len(gw.requests) == sent
    assert svc.get_state(TID)["next"] == ["await_answers"]
    assert svc.cancel("never-started") is False


def _fake_router_service() -> PipelineService:
    settings = AppSettings(_env_file=None, env="test", llm={"default_provider": "fake"})
    prices = PriceTable.from_file(settings.llm.prices_file)
    transport = FakeTransport({"rewrite": [FakeHang(30)]}, defaults_dir=PERSONA / "replies")
    registry = ProviderRegistry(
        settings,
        prices=prices,
        breakers=BreakerRegistry(),
        factories={"fake": lambda _s: transport},
    )
    router = LLMRouter(
        load_route_table(settings.llm, prices), registry, UsageRecorder(MemoryUsageSink(), prices)
    )
    deps = PipelineDeps(gateway=router, prompts=PromptLibrary(), settings=settings.pipeline)
    return PipelineService(build_graph(deps, new_checkpointer()), deps.runs)


def test_cancel_during_llm_call_under_1_5s():
    svc = _fake_router_service()
    _start(svc)
    assert svc.get_state(TID)["next"] == ["await_answers"]
    timer = threading.Timer(0.2, svc.cancel, (TID,))
    start = time.monotonic()
    timer.start()
    with pytest.raises(PipelineCancelled) as info:
        svc.resume(TID, "answers")
    elapsed = time.monotonic() - start
    timer.join()
    assert (info.value.node, info.value.when) == ("rewrite", "during")
    assert elapsed < 1.5


def test_progress_events_in_order():
    gw, svc = _service(_script())
    hooks = Recorder(svc, gw)
    _run_all(svc, hooks)
    pairs = [(e.node, e.phase) for e in hooks.events]
    expected = [(n, p) for n in SEQUENCE for p in ("started", "finished")]
    expected.insert(expected.index(("await_answers", "started")), ("await_answers", "started"))
    assert pairs == expected  # await_answers starts once before the pause, once on resume
    assert {e.session_id for e in hooks.events} == {TID}
    assert all(e.stage == NODE_STAGES[e.node][0] for e in hooks.events)
    progress = [e.progress for e in hooks.events]
    assert progress == sorted(progress) and progress[-1] == 100


def test_hook_failure_never_breaks_a_run():
    class Broken:
        async def before_node(self, event: ProgressEvent) -> None:
            raise RuntimeError("hook down")

        async def after_node(self, event: ProgressEvent) -> None:
            raise RuntimeError("hook down")

    _, svc = _service(_script())
    final = _run_all(svc, Broken())
    assert final["cover_letter"] is not None


def _container(script: dict[str, list[Outcome]]) -> Container:
    FakePdfRenderer.calls.clear()
    _, deps = deps_for(script)
    backend = backend_with_session(USER_A, TID, "job description")
    return Container(
        AppSettings(_env_file=None, env="test"),
        **backend.repos(),
        pipeline=PipelineService(build_graph(deps, new_checkpointer()), deps.runs),
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )


def test_generation_marks_cancelled():
    c = _container(_script(rewrite=[Hang(30)]))
    run_new_session(
        c,
        user_id=USER_A,
        thread_id=TID,
        profile=persona_profile(),
        job_description="job description",
        cover_letter=False,
        cover_letter_tone=None,
        cover_letter_length=None,
    )
    assert legacy_status_of(c.sessions, USER_A, TID) == "awaiting_hitl"
    timer = threading.Timer(0.2, c.pipeline.cancel, (TID,))
    timer.start()
    resume_after_answers(c, user_id=USER_A, thread_id=TID, reply="answers")
    timer.join()
    assert legacy_status_of(c.sessions, USER_A, TID) == "cancelled"
    summary = c.pipeline.summary(TID)
    assert summary is not None and summary.cancelled_stage == "rewrite"
    assert summary.error_code is None
    assert FakePdfRenderer.calls == []
    assert c.credits.ledger(USER_A) == []
