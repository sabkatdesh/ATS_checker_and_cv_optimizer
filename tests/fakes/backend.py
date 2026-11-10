from dataclasses import dataclass

from tests.fakes.fake_auth import TOKEN_A, FakeAuth
from tests.fakes.fake_llm import FakeStructuredLLM
from tests.fakes.fake_pipeline import FakePipeline
from tests.fakes.memory_store import MemoryStore


@dataclass
class FakeBackend:
    store: MemoryStore
    auth: FakeAuth
    pipeline: FakePipeline
    llm: FakeStructuredLLM


def auth_header(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
