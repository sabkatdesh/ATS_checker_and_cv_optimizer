"""The domain layer stands alone: it never imports the pipeline (or anything above it)."""

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[3] / "app" / "domain"
_UPPER = ("app.pipeline", "app.api", "app.adapters", "app.services", "app.container")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_no_domain_module_imports_an_upper_layer():
    offenders = {
        str(path.relative_to(DOMAIN)): name
        for path in DOMAIN.rglob("*.py")
        for name in _imports(path)
        if name.startswith(_UPPER)
    }
    assert offenders == {}


def test_warning_codes_live_in_the_domain_and_are_re_exported():
    from app.domain import warnings as domain_warnings
    from app.pipeline import warnings as pipeline_warnings

    assert pipeline_warnings.WarningCode is domain_warnings.WarningCode
