"""Walk every string inside a pydantic model: read them, or map them without revalidating."""

from collections.abc import Callable, Collection, Iterator
from enum import Enum
from typing import Any

from pydantic import BaseModel


def iter_strings(model: BaseModel, skip: Collection[str] = ()) -> Iterator[tuple[str, str]]:
    """Yield (path, text) pairs. Paths use field names only: list items and dict keys are masked."""
    for name in type(model).model_fields:
        if name not in skip:
            yield from _iter(getattr(model, name), name)


def _iter(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, Enum):
        return
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, BaseModel):
        for sub_path, text in iter_strings(value):
            yield f"{path}.{sub_path}", text
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _iter(item, f"{path}[]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter(key, f"{path}.<key>")
            yield from _iter(item, f"{path}.*")


def map_strings[M: BaseModel](model: M, fn: Callable[[str], str], skip: Collection[str] = ()) -> M:
    """Map every string value (not dict keys or enums); unchanged ones stay as they are."""
    update: dict[str, Any] = {}
    for name in type(model).model_fields:
        if name in skip:
            continue
        old = getattr(model, name)
        new = _map(old, fn)
        if new is not old:
            update[name] = new
    return model.model_copy(update=update) if update else model


def _map(value: Any, fn: Callable[[str], str]) -> Any:
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        new = fn(value)
        return value if new == value else new
    if isinstance(value, BaseModel):
        return map_strings(value, fn)
    if isinstance(value, list):
        items = [_map(item, fn) for item in value]
        return value if all(a is b for a, b in zip(items, value, strict=True)) else items
    if isinstance(value, dict):
        mapped = {key: _map(item, fn) for key, item in value.items()}
        return value if all(mapped[k] is v for k, v in value.items()) else mapped
    return value
