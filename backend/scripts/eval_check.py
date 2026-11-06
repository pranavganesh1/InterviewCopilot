"""Manual stability check for answer evaluation labels.

Usage (from backend/):
  uv run python scripts/eval_check.py --dry
  uv run python scripts/eval_check.py --dry --runs 3
  uv run python scripts/eval_check.py --runs 3          # real evaluator

Not run by pytest (see tests/test_eval_consistency.py::test_live_eval_...).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.interviewer import evaluate_answer  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval_samples.json"


def _load_samples() -> list[dict]:
    if FIXTURES.is_file():
        return json.loads(FIXTURES.read_text(encoding="utf-8"))
    # Tiny fallback if fixtures are missing.
    return [
        {
            "expected": "none",
            "answer": "I don't know",
            "question": "What is an array?",
            "topic": "arrays",
        }
    ]


async def _dry_run(samples: list[dict], runs: int) -> None:
    for sample in samples:
        expected = sample["expected"]
        for i in range(runs):
            print(
                f"run={i + 1} expected={expected:10} dry_label={expected:10} "
                f"topic={sample.get('topic', '')} answer={str(sample['answer'])[:50]!r}"
            )


async def _live_run(samples: list[dict], runs: int, model: str | None = None) -> None:
    for sample in samples:
        expected = sample["expected"]
        for i in range(runs):
            payload = {
                "mode": "strict",
                "brief": {"summary": sample.get("topic", "")},
                "last_question": sample["question"],
                "last_answer": sample["answer"],
            }
            if model:
                payload["model"] = model
            ev = await evaluate_answer(payload)
            print(
                f"run={i + 1} expected={expected:10} got={ev.coverage:10} "
                f"strengths={len(ev.strengths)} gaps={len(ev.gaps)} "
                f"topic={sample.get('topic', '')}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Print stubbed labels without calling the LLM",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Repeat each sample N times (default 1)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LiteLLM model alias for live runs (default structured-json)",
    )
    args = parser.parse_args()
    samples = _load_samples()
    runs = max(1, int(args.runs))
    asyncio.run(
        _dry_run(samples, runs) if args.dry else _live_run(samples, runs, model=args.model)
    )


if __name__ == "__main__":
    main()
