"""Manual stability check for answer evaluation labels.

Usage (from backend/):
  uv run python scripts/eval_check.py --dry     # stubbed labels, no network
  uv run python scripts/eval_check.py           # real evaluator (needs LLM)

Not run by pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow `python scripts/eval_check.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.interviewer import AnswerEvaluation, evaluate_answer  # noqa: E402

QUESTION = (
    "Given an array of integers, explain how you would find two indices whose "
    "values sum to a target. What is the time and space complexity?"
)

SAMPLES: list[tuple[str, str]] = [
    ("wrong", "I would sort the array and hope the first two numbers add up."),
    (
        "partial",
        "Use a hashmap of seen values. For each number check if target-num was seen.",
    ),
    (
        "correct",
        "One pass with a hash map from value→index. For each nums[i], look up "
        "target-nums[i]; if present return the pair of indices. O(n) time, O(n) space.",
    ),
    ("wrong", "Just print the array. Arrays are contiguous so the answer is obvious."),
    (
        "partial",
        "Brute force nested loops check every pair. That works but is slow for large n.",
    ),
    (
        "correct",
        "Two-sum: store complements in a dict while iterating once. Handle duplicates "
        "by recording indices carefully. Time O(n), space O(n).",
    ),
]


async def _dry_run() -> None:
    for expected, answer in SAMPLES:
        # Deterministic stub: mirror the labelled intent without calling the LLM.
        coverage = {
            "wrong": "none",
            "partial": "partial",
            "correct": "excellent",
        }[expected]
        print(f"expected={expected:8} dry_label={coverage:10} answer={answer[:60]}...")


async def _live_run() -> None:
    for expected, answer in SAMPLES:
        ev: AnswerEvaluation = await evaluate_answer(
            {
                "mode": "strict",
                "brief": {
                    "summary": "Arrays / hashing",
                    "question_areas": [{"topic": "Arrays", "guidance": "two-sum"}],
                },
                "last_question": QUESTION,
                "last_answer": answer,
            }
        )
        print(
            f"expected={expected:8} got={ev.coverage:10} "
            f"strengths={len(ev.strengths)} gaps={len(ev.gaps)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Print stubbed labels without calling the LLM",
    )
    args = parser.parse_args()
    asyncio.run(_dry_run() if args.dry else _live_run())


if __name__ == "__main__":
    main()
