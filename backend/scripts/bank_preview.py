"""Print a question bank for a few subjects so a person can spot-check it.

--dry uses fixed stub questions and does not call a model.
Without --dry the live track creator runs. Do not put an API key in the command.

    uv run python scripts/bank_preview.py --dry
"""

from __future__ import annotations

import argparse
import asyncio
import json

SUBJECTS = [
    "Python data structures",
    "ECE antenna design",
    "Retail pharmacy",
    "World history",
    "Physical geography",
    "Game design",
    "Clinical medicine",
    "Business strategy",
]

_STUBS = {
    "Python data structures": {
        "type": "conceptual",
        "question": "In Python, what happens if you slice a list beyond its length, and why?",
        "key_points": [
            "The slice stops at the end.",
            "It does not raise IndexError.",
            "The result is a shorter list.",
        ],
    },
    "ECE antenna design": {
        "type": "numeric",
        "question": "A 2 ohm resistor carries 2.5 A. What is the voltage drop?",
        "key_points": ["Ohm's law is V = IR.", "The current is 2.5 A.", "The drop is 5 V."],
    },
    "Retail pharmacy": {
        "type": "case_study",
        "question": "What counselling point matters most before the first dose?",
        "key_points": [
            "The case is generic, not a real patient.",
            "Name the main side effect.",
            "Say when to seek urgent care.",
        ],
    },
    "World history": {
        "type": "conceptual",
        "question": "In what year did the Berlin Wall open, and which border did that change?",
        "key_points": [
            "The year is 1989.",
            "It was 9 November.",
            "It divided East and West Berlin.",
        ],
    },
    "Physical geography": {
        "type": "mcq",
        "question": "Which ocean borders the west coast of South America?",
        "key_points": [
            "The ocean is the Pacific.",
            "It lies to the west.",
            "The Andes run along that coast.",
        ],
    },
    "Game design": {
        "type": "conceptual",
        "question": "What does a cooldown of 8 seconds limit in a player ability?",
        "key_points": [
            "The ability cannot be reused immediately.",
            "The wait is 8 seconds.",
            "It is a pacing rule, not a story fact.",
        ],
    },
    "Clinical medicine": {
        "type": "case_study",
        "question": "Which single finding in this generic vignette needs urgent review?",
        "key_points": [
            "This is exam practice, not advice for a real patient.",
            "Name one red-flag finding.",
            "Do not invent a personal diagnosis.",
        ],
    },
    "Business strategy": {
        "type": "case_study",
        "question": "What is the main trade-off in keeping the higher price?",
        "key_points": [
            "Margin rises if volume holds.",
            "Volume may fall.",
            "The case is fictional.",
        ],
    },
}


def _dry_rows() -> list[dict]:
    rows = []
    for subject in SUBJECTS:
        stub = _STUBS[subject]
        rows.append({"subject": subject, **stub})
    return rows


async def _live_rows() -> list[dict]:
    from app.services.track_service import build_track_creator_brief

    rows = []
    for subject in SUBJECTS:
        brief = await build_track_creator_brief(
            objective={"track_type": "topic", "subject": subject}, vault_summary=[]
        )
        for question in brief.get("question_bank") or []:
            rows.append(
                {
                    "subject": subject,
                    "type": question.get("type"),
                    "question": question.get("question"),
                    "key_points": question.get("key_points") or [],
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview questions for several subjects.")
    parser.add_argument("--dry", action="store_true", help="Print stubbed questions only.")
    args = parser.parse_args()
    rows = _dry_rows() if args.dry else asyncio.run(_live_rows())
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
