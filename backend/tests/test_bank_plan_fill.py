"""A short bank plus a 15-slot plan still yields 15 distinct questions."""

import pytest

from app.agents.interviewer import TurnDecision, run_interviewer_turn
from app.agents.question_dedupe import is_duplicate_question
from app.agents.question_plan import deterministic_question_plan

BRIEF = {
    "summary": "Systems interviews",
    "question_areas": [
        {"topic": "Hashing", "guidance": "collisions"},
        {"topic": "Trees", "guidance": "balance"},
        {"topic": "Scheduling", "guidance": "fairness"},
    ],
    "competencies": [{"name": "Complexity", "description": "Big-O", "importance": "core"}],
}

BANK = [
    {
        "area": "Hashing",
        "question": "Why does a hash table use chaining or open addressing for collisions?",
        "type": "conceptual",
    },
    {
        "area": "Trees",
        "question": "When is a balanced search tree preferable to a hash map for range queries?",
        "type": "conceptual",
    },
    {
        "area": "Indexes",
        "question": "How does a B-tree keep disk reads low for database indexes?",
        "type": "conceptual",
    },
    {
        "area": "Trees",
        "question": "What color invariant does a red-black tree maintain during insertion?",
        "type": "conceptual",
    },
    {
        "area": "Hashing",
        "question": (
            "Why does a hash table use chaining or open addressing for collisions? Elaborate."
        ),
        "type": "conceptual",
    },
]


def _generated(n: int) -> str:
    topics = [
        "orbital kettle calibration",
        "lighthouse foghorn timing",
        "subway token dispensers",
        "glacier core labeling",
        "violin string tension",
        "harbor crane scheduling",
        "desert well pumps",
        "library card catalogs",
        "bakery oven queues",
        "river lock chambers",
        "museum lamp circuits",
    ]
    return (
        f"Design a fresh approach number {n} for {topics[n % len(topics)]} "
        f"and state one constraint unique to case {n * 17 + 3}."
    )


@pytest.mark.asyncio
async def test_bank_then_generated_fills_fifteen_distinct(monkeypatch):
    plan = deterministic_question_plan(BRIEF, 15)
    counter = {"n": 0}

    async def fake_structured(*_args, **_kwargs):
        n = counter["n"]
        counter["n"] += 1
        return TurnDecision(
            evaluation={"coverage": "partial", "strengths": [], "gaps": ["thin example"]},
            decision="complete",
            next_question=_generated(n),
            question_area="Generated",
        )

    monkeypatch.setattr("app.agents.interviewer.structured_completion", fake_structured)

    asked: list[str] = []
    for index in range(15):
        payload = {
            "mode": "strict",
            "brief": BRIEF,
            "asked_questions": list(asked),
            "question_bank": [
                entry
                for entry in BANK
                if entry["question"] not in set(asked)
            ],
            "questions_asked": index,
            "questions_remaining": 15 - index,
            "question_plan_slot": plan[index],
            "last_answer": None
            if index == 0
            else "A concrete answer long enough to pass the short-answer guard.",
            "transcript": [],
            "turns_in_current_area": 0,
            "remaining_areas": ["Hashing"],
            "covered_areas": [],
        }
        decision = await run_interviewer_turn(payload=payload)
        assert decision.decision != "complete"
        asked.append(decision.next_question)

    assert asked[:4] == [entry["question"] for entry in BANK[:4]]
    assert len(asked) == 15
    assert len(set(asked)) == 15
    for i, question in enumerate(asked):
        assert not is_duplicate_question(question, asked[:i])
    # The paraphrased fifth bank entry was skipped.
    assert BANK[4]["question"] not in asked


@pytest.mark.asyncio
async def test_no_bank_keeps_the_generated_question(monkeypatch):
    async def fake_structured(*_args, **_kwargs):
        return TurnDecision(
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            decision="next_area",
            next_question="What is a hashmap collision chain?",
            question_area="Hashing",
        )

    monkeypatch.setattr("app.agents.interviewer.structured_completion", fake_structured)
    decision = await run_interviewer_turn(
        payload={
            "mode": "strict",
            "brief": BRIEF,
            "asked_questions": [],
            "question_bank": [],
            "questions_asked": 0,
            "questions_remaining": 15,
            "last_answer": None,
            "transcript": [],
            "turns_in_current_area": 0,
        }
    )
    assert decision.next_question == "What is a hashmap collision chain?"


@pytest.mark.asyncio
async def test_generated_duplicate_is_replaced(monkeypatch):
    repeated = "Explain the core idea behind harbor cranes with a concrete example."

    async def fake_structured(*_args, **_kwargs):
        return TurnDecision(
            evaluation={"coverage": "partial", "strengths": [], "gaps": ["same idea"]},
            decision="next_area",
            next_question=repeated,
            question_area="Cranes",
        )

    monkeypatch.setattr("app.agents.interviewer.structured_completion", fake_structured)
    decision = await run_interviewer_turn(
        payload={
            "mode": "strict",
            "brief": BRIEF,
            "asked_questions": [repeated],
            "question_bank": [],
            "questions_asked": 1,
            "questions_remaining": 14,
            "last_answer": "A concrete answer long enough to pass the short-answer guard.",
            "transcript": [{"area": "Cranes", "question": repeated, "answer": "prior"}],
            "turns_in_current_area": 1,
            "remaining_areas": ["Scheduling"],
        }
    )
    assert not is_duplicate_question(decision.next_question, [repeated])
