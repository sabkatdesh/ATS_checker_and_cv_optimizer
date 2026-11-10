from dataclasses import dataclass

from app.ports.auth import TokenVerifier
from app.ports.legacy_store import LegacyStore
from app.ports.llm_legacy import StructuredLLM
from app.ports.pipeline import PipelineRunner
from app.ports.rendering import CoverLetterRenderer, CvPdfRenderer
from tests.fakes.fake_auth import TOKEN_A, FakeAuth
from tests.fakes.fake_llm import FakeStructuredLLM
from tests.fakes.fake_pipeline import FakePipeline
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_store import MemoryStore

# Type-conformance checks: drift between the fakes and the ports fails mypy.
_store: LegacyStore = MemoryStore()
_auth: TokenVerifier = FakeAuth()
_pipeline: PipelineRunner = FakePipeline()
_llm: StructuredLLM = FakeStructuredLLM()
_pdf: CvPdfRenderer = FakePdfRenderer()
_cover_letter: CoverLetterRenderer = FakeCoverLetterRenderer()


@dataclass
class FakeBackend:
    store: MemoryStore
    auth: FakeAuth
    pipeline: FakePipeline
    llm: FakeStructuredLLM


def auth_header(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
