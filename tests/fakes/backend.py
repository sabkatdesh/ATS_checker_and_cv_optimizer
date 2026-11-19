from dataclasses import dataclass, field

from app.ports.auth import TokenVerifier
from app.ports.legacy_store import LegacyStore
from app.ports.llm import LLMGateway
from app.ports.pipeline import PipelineRunner
from app.ports.rendering import CoverLetterRenderer, CvPdfRenderer
from tests.fakes.fake_auth import TOKEN_A, FakeAuth
from tests.fakes.fake_blob_storage import FakeBlobStorage
from tests.fakes.fake_pipeline import FakePipeline
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_repos import MemoryMasterProfileRepo, MemoryProfileRepo, MemoryTemplateRepo
from tests.fakes.memory_store import MemoryStore
from tests.pipeline.scripted_gateway import ScriptedGateway

# Type-conformance checks: drift between the fakes and the ports fails mypy.
_store: LegacyStore = MemoryStore()
_auth: TokenVerifier = FakeAuth()
_pipeline: PipelineRunner = FakePipeline()
_llm: LLMGateway = ScriptedGateway({})
_pdf: CvPdfRenderer = FakePdfRenderer()
_cover_letter: CoverLetterRenderer = FakeCoverLetterRenderer()


@dataclass
class FakeBackend:
    store: MemoryStore
    auth: FakeAuth
    pipeline: FakePipeline
    llm: ScriptedGateway
    storage: FakeBlobStorage = field(default_factory=FakeBlobStorage)
    profiles: MemoryProfileRepo = field(default_factory=MemoryProfileRepo)
    master_profiles: MemoryMasterProfileRepo = field(default_factory=MemoryMasterProfileRepo)
    templates: MemoryTemplateRepo = field(default_factory=MemoryTemplateRepo)


def auth_header(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
