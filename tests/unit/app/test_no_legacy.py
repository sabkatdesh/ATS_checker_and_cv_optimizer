import ast
import importlib
import re
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LEGACY_IMPORT = re.compile(r"^\s*(from|import) (core|services|database|api)\b", re.M)


def test_legacy_paths_gone():
    for name in ("api.py", "database.py", "core", "services"):
        assert not (ROOT / name).exists(), name


def test_no_legacy_imports():
    offenders = []
    for folder in ("app", "tests", "scripts"):
        for path in (ROOT / folder).rglob("*.py"):
            if path.name == "test_no_legacy.py":
                continue
            if LEGACY_IMPORT.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_no_print_in_app():
    offenders = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "app").rglob("*.py")
        if re.search(r"(?<![\w.])print\(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


DELETED_MODULES = (
    "app.adapters.llm.langchain_bridge",
    "app.adapters.llm.legacy_structured",
    "app.ports.llm_legacy",
    "app.pipeline.chains",
    "app.pipeline.prompts.extraction",
    "app.pipeline.prompts.rewrite",
    "app.pipeline.prompts.cover_letter",
    "tests.fakes.fake_chat_model",
    "tests.fakes.fake_llm",
)
BRIDGE_NAMES = {"safe_llm_parse", "StructuredLLM", "GatewayChatModel", "GatewayStructuredLLM"}


@pytest.mark.parametrize("module", DELETED_MODULES)
def test_bridge_modules_deleted(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_prompts_package_has_no_reexports():
    import app.pipeline.prompts as prompts

    public = {n: v for n, v in vars(prompts).items() if not n.startswith("_")}
    assert [n for n, v in public.items() if not isinstance(v, types.ModuleType)] == []


def test_no_legacy_canned_replies():
    assert list((ROOT / "app/adapters/llm/fake_responses").glob("legacy.*")) == []


def _app_trees():
    for path in (ROOT / "app").rglob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_no_langchain_core_import_in_app():
    offenders = []
    for path, tree in _app_trees():
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] == "langchain_core" for n in names):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_no_bridge_names_in_app():
    offenders = set()
    for path, tree in _app_trees():
        for node in ast.walk(tree):
            name = getattr(node, "id", None) or getattr(node, "attr", None)
            name = name or getattr(node, "name", None)
            if isinstance(node, ast.alias):
                name = node.asname or node.name.rsplit(".", 1)[-1]
            if name in BRIDGE_NAMES:
                offenders.add(str(path.relative_to(ROOT)))
    assert sorted(offenders) == []
