"""Print sample persona-styled questions for manual style review.

Usage:
  cd backend
  uv run python scripts/persona_preview.py --dry
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.persona import PERSONAS, bias_plan_for_persona, persona_prompt_block
from app.services import probe as probe_service

SUBJECT = "Operating systems"
SAMPLE_ANSWER = (
    "I would use a hash map to track process ids so lookups stay constant time under load."
)
SAMPLE_VAULT = [
    {
        "category": "project",
        "title": "Campus process monitor",
        "details": {"stack": "Go + eBPF", "outcome": "cut alert noise 40%"},
    }
]
BASE_PLAN = [
    {"topic": "Process scheduling", "objective": "explain fairness", "format": "conceptual"},
    {"topic": "System reliability", "objective": "failure modes", "format": "case_study"},
    {"topic": "Team ownership", "objective": "delivery impact", "format": "behavioral"},
    {"topic": "Complexity bounds", "objective": "why O(1)", "format": "numeric"},
    {"topic": "Memory layout", "objective": "define pages", "format": "conceptual"},
    {"topic": "Locks", "objective": "deadlocks", "format": "conceptual"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="Stubbed local templates only.")
    args = parser.parse_args()
    _ = args.dry

    print(f"Subject: {SUBJECT}\n")
    for persona in PERSONAS.values():
        print("=" * 60)
        print(f"{persona.name} ({persona.id})")
        print(persona.description)
        print("Focus:", ", ".join(persona.focus_tags))
        block = persona_prompt_block(persona.id, mode="strict")
        print("Prompt block:", "(none — Balanced)" if not block else block.splitlines()[0])
        plan = bias_plan_for_persona([dict(s) for s in BASE_PLAN], persona.id)
        print("Early plan topics:", " → ".join(s["topic"] for s in plan[:3]))
        samples = []
        ans = probe_service.craft_answer_probe(
            answer=SAMPLE_ANSWER,
            area="Scheduling",
            asked=[],
            mode="strict",
            seed=0,
            persona_id=persona.id,
        )
        if ans:
            samples.append(ans["next_question"])
        res = probe_service.craft_resume_probe(
            items=SAMPLE_VAULT,
            area="Projects",
            asked=[],
            mode="strict",
            seed=0,
            persona_id=persona.id,
        )
        if res:
            samples.append(res["next_question"])
        weak = probe_service.craft_weakness_retest(
            weak_concepts=["deadlocks"], asked=[], mode="strict", seed=1
        )
        if weak:
            samples.append(weak["next_question"])
        while len(samples) < 3:
            samples.append("(fallback skipped)")
        for i, q in enumerate(samples[:3], 1):
            print(f"  {i}. {q}")
        print()


if __name__ == "__main__":
    main()
