from dataclasses import dataclass, field
from typing import Any

from app.ports.auth import TokenVerifier
from app.ports.llm import LLMGateway
from app.ports.pipeline import PipelineRunner
from app.ports.rendering import CoverLetterRenderer, CvPdfRenderer
from app.ports.repositories import (
    CreditReadRepo,
    GuardRepo,
    MasterProfileRepo,
    ProfileRepo,
    RenderRepo,
    SessionRepo,
    TemplateRepo,
)
from tests.fakes.fake_auth import TOKEN_A, FakeAuth
from tests.fakes.fake_blob_storage import FakeBlobStorage
from tests.fakes.fake_pipeline import FakePipeline
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_repos import (
    MemoryCreditRepo,
    MemoryGuardRepo,
    MemoryMasterProfileRepo,
    MemoryProfileRepo,
    MemoryTemplateRepo,
)
from tests.fakes.memory_session_repos import MemoryRenderRepo, MemorySessionRepo
from tests.pipeline.scripted_gateway import ScriptedGateway

# Type-conformance checks: drift between the fakes and the ports fails mypy.
_auth: TokenVerifier = FakeAuth()
_pipeline: PipelineRunner = FakePipeline()
_llm: LLMGateway = ScriptedGateway({})
_pdf: CvPdfRenderer = FakePdfRenderer()
_cover_letter: CoverLetterRenderer = FakeCoverLetterRenderer()
_profiles: ProfileRepo = MemoryProfileRepo()
_master: MasterProfileRepo = MemoryMasterProfileRepo()
_templates: TemplateRepo = MemoryTemplateRepo()
_sessions: SessionRepo = MemorySessionRepo()
_renders: RenderRepo = MemoryRenderRepo()
_credits: CreditReadRepo = MemoryCreditRepo()
_guards: GuardRepo = MemoryGuardRepo()


@dataclass
class FakeBackend:
    auth: FakeAuth = field(default_factory=FakeAuth)
    pipeline: FakePipeline = field(default_factory=FakePipeline)
    llm: ScriptedGateway = field(default_factory=lambda: ScriptedGateway({}))
    storage: FakeBlobStorage = field(default_factory=FakeBlobStorage)
    profiles: MemoryProfileRepo = field(default_factory=MemoryProfileRepo)
    master_profiles: MemoryMasterProfileRepo = field(default_factory=MemoryMasterProfileRepo)
    templates: MemoryTemplateRepo = field(default_factory=MemoryTemplateRepo)
    renders: MemoryRenderRepo = field(default_factory=MemoryRenderRepo)
    sessions: MemorySessionRepo = field(init=False)
    credits: MemoryCreditRepo = field(default_factory=MemoryCreditRepo)
    guards: MemoryGuardRepo = field(default_factory=MemoryGuardRepo)

    def __post_init__(self) -> None:
        self.sessions = MemorySessionRepo(self.renders)

    def repos(self) -> dict[str, Any]:
        """Container keyword overrides for every fake persistence port."""
        return {
            "auth": self.auth,
            "storage": self.storage,
            "profiles": self.profiles,
            "master_profiles": self.master_profiles,
            "templates": self.templates,
            "sessions": self.sessions,
            "renders": self.renders,
            "credits": self.credits,
            "guards": self.guards,
        }


def auth_header(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def backend_with_session(user_id: str, session_id: str, jd_text: str = "jd") -> FakeBackend:
    """A FakeBackend holding one running session, as /sessions/start leaves it."""
    backend = FakeBackend()
    backend.sessions.create(
        user_id, session_id, jd_text=jd_text, source_cv={}, options={}, template_id="classic"
    )
    return backend


def legacy_status_of(sessions: SessionRepo, user_id: str, session_id: str) -> str | None:
    """The status string the API would return for this session."""
    from app.domain.sessions.status import legacy_status

    row = sessions.get(user_id, session_id)
    return legacy_status(row.status, row.awaiting_kind) if row else None
