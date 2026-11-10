"""Print sample Socratic probes for a fake vault (manual quality check).

Usage:
  cd backend
  uv run python scripts/probe_preview.py --dry
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `uv run python scripts/probe_preview.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import probe as probe_service

SAMPLE_VAULT = [
    {
        "category": "project",
        "title": "Campus navigation app",
        "details": {
            "role": "backend",
            "stack": "FastAPI + Postgres",
            "outcome": "cut average route time by 18%",
        },
    },
    {
        "category": "project",
        "title": "Line-following robot",
        "details": {"stack": "Arduino", "challenge": "noisy IR sensors"},
    },
    {
        "category": "skill",
        "title": "PostgreSQL indexing",
        "details": {"level": "intermediate"},
    },
]

SAMPLE_ANSWERS = [
    "I used a hash map so I could look up student ids in constant time.",
    "We chose Postgres over Mongo because we needed transactions for enrollments.",
    "I would cache the hottest routes in Redis with a short TTL.",
    "The robot used a PID loop on the IR error signal.",
    "I denormalized the schedule table to avoid a join on every request.",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Use stubbed local templates only (default behaviour).",
    )
    args = parser.parse_args()
    _ = args.dry  # reserved for a future live LLM path

    items = SAMPLE_VAULT
    print("=== Resume / project probes ===")
    for i in range(5):
        probe = probe_service.craft_resume_probe(
            items=items, area="Projects", asked=[], mode="strict", seed=i
        )
        print(f"{i + 1}. {probe['next_question'] if probe else '(none)'}")

    print("\n=== Answer follow-up probes ===")
    for i, answer in enumerate(SAMPLE_ANSWERS):
        probe = probe_service.craft_answer_probe(
            answer=answer, area="Systems", asked=[], mode="strict", seed=i
        )
        print(f"{i + 1}. {probe['next_question'] if probe else '(none)'}")

    print("\nVault block preview (truncated):")
    print(probe_service.vault_prompt_block(items)[:400], "...")


if __name__ == "__main__":
    main()
