"""Enforce file-length limits: strict under app/, advisory elsewhere."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path


def check(
    paths: Iterable[Path],
    *,
    strict_roots: tuple[str, ...] = ("app",),
    limit: int = 300,
    fail: int = 400,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for .py files exceeding the limits."""
    errors: list[str] = []
    warnings: list[str] = []
    for path in paths:
        if path.suffix != ".py":
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())
        shown = path.as_posix()
        if path.parts and path.parts[0] in strict_roots:
            if count > limit:
                errors.append(f"{shown}: {count} lines (max {limit})")
        elif count > fail:
            errors.append(f"{shown}: {count} lines (max {fail})")
        elif count > limit:
            warnings.append(f"{shown}: {count} lines (over {limit})")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    roots = argv if argv else ["app", "tests", "scripts"]
    files = [p for root in roots for p in sorted(Path(root).rglob("*.py"))]
    errors, warnings = check(files)
    for line in warnings:
        print(f"warning: {line}")
    for line in errors:
        print(f"error: {line}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
