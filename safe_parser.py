import json
import re


def safe_llm_parse(raw_text: str, model_class, fallback):
    """
    Try to parse LLM raw string into a Pydantic model.
    Never crashes. Returns fallback if all attempts fail.

    3 attempts:
    1. Direct json.loads  (LLM gave clean JSON)
    2. Strip markdown ```json ... ``` block  (LLM wrapped it in markdown)
    3. Find first { ... } in the text  (LLM added explanation around the JSON)
    """

    # ── Attempt 1: direct JSON parse ──────────────────────────────
    try:
        data = json.loads(raw_text)
        return model_class.model_validate(data)
    except Exception:
        pass

    # ── Attempt 2: JSON inside markdown code block ─────────────────
    match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', raw_text)
    if match:
        try:
            data = json.loads(match.group(1))
            return model_class.model_validate(data)
        except Exception:
            pass

    # ── Attempt 3: find any { ... } block in the text ─────────────
    match = re.search(r'\{[\s\S]+\}', raw_text)
    if match:
        try:
            data = json.loads(match.group(0))
            return model_class.model_validate(data)
        except Exception:
            pass

    # ── All failed: return the fallback, never crash ───────────────
    print(f"⚠️  Could not parse {model_class.__name__} from LLM output. Using fallback.")
    return fallback