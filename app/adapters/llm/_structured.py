"""Structured-output helpers: provider schema, prompt-mode instruction, parse and repair.

Error text built here never contains model or user text, only paths and constant phrases.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ports.llm import Message
from app.ports.llm_errors import LLMOutputInvalid

# Rejected by the provider's constrained decoding; enforced afterwards by Pydantic.
STRIP_KEYWORDS: frozenset[str] = frozenset(
    {"maxItems", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
)

JSON_INSTRUCTION = (
    "Respond with a single JSON object that conforms to the JSON Schema below. "
    "Output only the JSON, with no commentary and no code fences.\nJSON Schema:\n"
)
REPAIR_TEXT = (
    "Your previous reply was not valid. Reply again with only a corrected JSON object "
    "that conforms to the schema. Problems found:\n"
)
_MAX_ERROR_LINES = 10
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


_NAME_MAPS = frozenset({"properties", "$defs"})


def _clean(node: Any, strip: frozenset[str]) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in strip:
                continue
            if key in _NAME_MAPS and isinstance(value, dict):
                # name -> schema maps: never filter the names, only clean the schemas
                out[key] = {name: _clean(sub, strip) for name, sub in value.items()}
            else:
                out[key] = _clean(value, strip)
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_clean(v, strip) for v in node]
    return node


def provider_schema(
    model: type[BaseModel], *, strip: frozenset[str] = STRIP_KEYWORDS
) -> dict[str, Any]:
    """JSON schema for provider constrained decoding.

    Removes `strip` keywords (enforced later by Pydantic) and sets additionalProperties=false on
    every object, which overwrites a schema-valued additionalProperties: dict[str, X] fields
    become empty objects, so avoid them in provider-bound models.
    """
    schema: dict[str, Any] = _clean(model.model_json_schema(), strip)
    return schema


def json_instruction(schema: dict[str, Any]) -> str:
    return JSON_INSTRUCTION + json.dumps(schema)


def _extract_json(text: str) -> str:
    fenced = _FENCE.search(text)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    if candidate.startswith(("{", "[")):
        return candidate
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        return candidate[start : end + 1]
    return candidate


def _error_summary(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors(include_input=False)[:_MAX_ERROR_LINES]:
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"{loc}: {err['msg']}")
    return "\n".join(lines)


def parse_structured[T: BaseModel](text: str, model: type[T]) -> T:
    try:
        data = json.loads(_extract_json(text))
    except json.JSONDecodeError as exc:
        raise LLMOutputInvalid(
            f"invalid JSON at line {exc.lineno} column {exc.colno} (position {exc.pos})"
        ) from None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise LLMOutputInvalid(_error_summary(exc)) from None


def repair_turns(messages: list[Message], bad_text: str, error_summary: str) -> list[Message]:
    return [
        *messages,
        Message(role="assistant", content=bad_text),
        Message(role="user", content=REPAIR_TEXT + error_summary),
    ]
