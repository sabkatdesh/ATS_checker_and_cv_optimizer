import asyncio
from typing import Any

from app.config.pipeline_settings import PipelineSettings
from app.domain.jd.schemas import JobDescriptionStructured
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.prompts.loader import PromptLibrary
from app.ports.llm import CancelToken
from tests.pipeline.scripted_gateway import ScriptedGateway


def setup() -> tuple[ScriptedGateway, PipelineDeps, RunContext]:
    gw = ScriptedGateway({"jd_extract": [JobDescriptionStructured(job_title="Nurse")]})
    deps = PipelineDeps(gateway=gw, prompts=PromptLibrary(), settings=PipelineSettings())
    return gw, deps, RunContext(session_id="s-1", cancel=CancelToken())


def run(deps: PipelineDeps, ctx: RunContext, text: str = "JD") -> Any:
    return asyncio.run(
        call_step(
            deps,
            ctx,
            step="jd_extract",
            schema=JobDescriptionStructured,
            blocks=[("job_description", text)],
        )
    )


def test_returns_typed_output() -> None:
    _, deps, ctx = setup()
    out = run(deps, ctx)
    assert isinstance(out, JobDescriptionStructured)
    assert out.job_title == "Nurse"


def test_request_shape() -> None:
    gw, deps, ctx = setup()
    run(deps, ctx)
    req = gw.requests[0]
    prompt = deps.prompts.get("jd_extract")
    assert req.step == "jd_extract"
    assert req.system == prompt.system
    assert len(req.messages) == 1
    assert req.messages[0].role == "user"
    assert req.output_schema is JobDescriptionStructured
    assert req.metadata.prompt_id == "jd_extract"
    assert req.metadata.prompt_version == prompt.version
    assert req.metadata.session_id == ctx.session_id


def test_user_text_never_in_system() -> None:
    gw, deps, ctx = setup()
    run(deps, ctx, "SENTINEL-JD")
    req = gw.requests[0]
    assert "SENTINEL-JD" not in req.system
    assert "SENTINEL-JD" in req.messages[0].content


def test_passes_cancel_token() -> None:
    gw, deps, ctx = setup()
    run(deps, ctx)
    assert gw.cancel_tokens[0] is ctx.cancel
