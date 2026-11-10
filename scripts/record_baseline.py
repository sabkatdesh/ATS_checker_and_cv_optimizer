"""
Run the existing pipeline against all tech test pairs and save outputs as
regression baselines. Run this after Phase 1 (LLM migration) to capture the
GPT-5 mini baseline before further changes.

Usage:
    python scripts/record_baseline.py

Outputs to: data/test_set/baselines/{id}_baseline.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_SET_DIR = Path("data/test_set")
BASELINE_DIR = TEST_SET_DIR / "baselines"
TECH_PAIRS = ["tech_junior.json", "tech_senior.json", "tech_fresher.json", "tech_poor_format.json"]


def load_test_pair(filename: str) -> dict:
    with open(TEST_SET_DIR / filename) as f:
        return json.load(f)


def run_pipeline_on_pair(pair: dict) -> dict:
    """Run the pipeline synchronously and return the final state."""
    import asyncio

    from main_pipeline_hitl_supabase import get_pipeline_state, run_pipeline_for_user

    user_id = "baseline_test_user"
    thread_id = f"baseline_{pair['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    asyncio.run(
        run_pipeline_for_user(
            user_id=user_id,
            thread_id=thread_id,
            jd_text=pair["jd_text"],
            cv_text=pair["cv_text"],
        )
    )

    state = asyncio.run(get_pipeline_state(thread_id))
    return state


def main():
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for filename in TECH_PAIRS:
        pair_path = TEST_SET_DIR / filename
        if not pair_path.exists():
            print(f"  SKIP {filename} — file not found")
            continue

        pair = load_test_pair(filename)
        print(f"Running pipeline on: {pair['id']} ...")

        try:
            state = run_pipeline_on_pair(pair)
            result = {
                "id": pair["id"],
                "recorded_at": datetime.now().isoformat(),
                "status": state.get("status"),
                "overall_ats_score": state.get("overall_match_score"),
                "section_scores": state.get("section_scores"),
                "hard_gaps": state.get("hard_gaps"),
                "rewrite_iterations": state.get("rewrite_count"),
                "word_count_final": len(state.get("rewritten_cv", "").split()),
                "token_cost_input": state.get("token_cost_input"),
                "token_cost_output": state.get("token_cost_output"),
            }
            output_path = BASELINE_DIR / f"{pair['id']}_baseline.json"
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"  Saved baseline: {output_path}")
            results.append(result)
        except Exception as e:
            print(f"  ERROR on {pair['id']}: {e}")

    print(f"\nBaseline recording complete. {len(results)}/{len(TECH_PAIRS)} pairs succeeded.")
    summary_path = BASELINE_DIR / "summary.json"
    with open(summary_path, "w") as f:
        json.dump({"recorded_at": datetime.now().isoformat(), "results": results}, f, indent=2)
    print(f"Summary saved: {summary_path}")


if __name__ == "__main__":
    main()
