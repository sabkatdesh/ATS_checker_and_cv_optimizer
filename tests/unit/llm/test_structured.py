import json

import pytest
from pydantic import BaseModel, Field

from app.adapters.llm._structured import (
    json_instruction,
    parse_structured,
    provider_schema,
    repair_turns,
)
from app.ports.llm import Message
from app.ports.llm_errors import LLMOutputInvalid


class Item(BaseModel):
    name: str = Field(max_length=20, min_length=1)
    score: int = Field(ge=0, le=10)


class GapQuestionsLike(BaseModel):
    questions: list[str] = Field(max_length=5)
    items: list[Item]
    title: str = Field(max_length=50)


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_schema_strips_configured_keywords():
    schema = provider_schema(GapQuestionsLike)
    for d in _walk(schema):
        for kw in ("maxItems", "minimum", "maximum"):
            assert kw not in d
    assert any("maxLength" in d for d in _walk(schema))  # not stripped


def test_schema_sets_additional_properties_false_on_objects():
    schema = provider_schema(GapQuestionsLike)
    objs = [d for d in _walk(schema) if d.get("type") == "object"]
    assert len(objs) >= 2
    assert all(d["additionalProperties"] is False for d in objs)


def test_parse_valid_json():
    out = parse_structured('{"name": "a", "score": 3}', Item)
    assert out == Item(name="a", score=3)


def test_parse_fenced_json():
    text = 'Here you go:\n```json\n{"name": "a", "score": 3}\n```\nDone.'
    assert parse_structured(text, Item).score == 3


def test_parse_json_with_surrounding_prose():
    assert parse_structured('Sure! {"name": "a", "score": 3} hope it helps', Item).name == "a"


def test_parse_invalid_json_raises_with_position_not_text():
    with pytest.raises(LLMOutputInvalid) as ei:
        parse_structured('{"name": "SENTINEL", oops', Item)
    assert "SENTINEL" not in str(ei.value)
    assert "SENTINEL" not in ei.value.detail
    assert "position" in ei.value.detail or "line" in ei.value.detail


def test_parse_schema_violation_lists_paths_not_values():
    bad = json.dumps({"name": "SENTINEL" * 5, "score": 99})
    with pytest.raises(LLMOutputInvalid) as ei:
        parse_structured(bad, Item)
    detail = ei.value.detail
    assert "name:" in detail and "score:" in detail
    assert "SENTINEL" not in detail and "99" not in detail
    assert len(detail.splitlines()) <= 10


def test_repair_turns_end_with_user_and_include_errors():
    msgs = [Message(role="user", content="hi")]
    out = repair_turns(msgs, "bad", "score: too big")
    assert [m.role for m in out] == ["user", "assistant", "user"]
    assert out[1].content == "bad"
    assert "score: too big" in out[-1].content
    assert len(msgs) == 1


def test_json_instruction_contains_schema_and_no_user_text():
    schema = provider_schema(Item)
    text = json_instruction(schema)
    assert json.dumps(schema) in text
    assert "JSON" in text
