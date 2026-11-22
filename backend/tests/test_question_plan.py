"""Question plan builder + interview_service payload wiring."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.interviewer import TurnDecision
from app.agents.question_plan import build_question_plan, deterministic_question_plan

BRIEF = {
    "summary": "Arrays and hashing",
    "question_areas": [
        {"topic": "Array Basics", "guidance": "memory layout"},
        {"topic": "Two Pointers", "guidance": "sorted arrays"},
        {"topic": "Hash Maps", "guidance": "collisions"},
    ],
    "competencies": [
        {"name": "Complexity", "description": "Big-O", "importance": "core"},
    ],
}


def test_deterministic_plan_returns_n_slots():
    slots = deterministic_question_plan(BRIEF, 15)
    assert len(slots) == 15
    assert slots[0]["difficulty"] == "foundational"
    assert slots[-1]["difficulty"] == "advanced"
    topics = {s["topic"] for s in slots}
    assert "Array Basics" in topics
    assert "Complexity" in topics
    objectives = [s["objective"] for s in slots]
    assert len(set(objectives)) == 15


def test_deterministic_plan_uses_topic_blocks():
    """Subjects run in consecutive blocks, not round-robin one-by-one."""
    slots = deterministic_question_plan(BRIEF, 15, duration_minutes=60)
    runs: list[tuple[str, int]] = []
    for slot in slots:
        topic = slot["topic"]
        if runs and runs[-1][0] == topic:
            runs[-1] = (topic, runs[-1][1] + 1)
        else:
            runs.append((topic, 1))
    # Complete blocks should stay in the duration-aware depth window.
    for topic, count in runs[:-1]:
        assert 2 <= count <= 4, (topic, count, runs)
    assert runs[-1][1] >= 1
    assert len(runs) >= 3


def test_thin_brief_gets_multiple_subjects():
    thin = {
        "summary": "Python programming interview",
        "question_areas": [{"topic": "Python", "guidance": "language basics"}],
        "competencies": [],
    }
    slots = deterministic_question_plan(thin, 12, duration_minutes=60)
    topics = {s["topic"] for s in slots}
    assert len(topics) >= 3
    assert "Python" in topics


def test_short_duration_covers_fewer_subjects_than_long():
    from app.agents.question_plan import target_subject_count

    assert target_subject_count(15, 20) < target_subject_count(15, 90)


def test_physics_brief_stays_on_physics_subjects():
    physics = {
        "summary": "Undergraduate physics interview",
        "question_areas": [
            {"topic": "Classical Mechanics", "guidance": "Newton laws"},
            {"topic": "Electromagnetism", "guidance": "Maxwell"},
            {"topic": "Quantum Mechanics", "guidance": "wavefunctions"},
        ],
        "competencies": [{"name": "Mathematical Methods", "description": "LA", "importance": "core"}],
    }
    slots = deterministic_question_plan(physics, 12, duration_minutes=45)
    topics = {s["topic"] for s in slots}
    assert "Classical Mechanics" in topics
    assert "Electromagnetism" in topics
    # Must not inject CS-only subjects.
    assert "Data Structures and Algorithms" not in topics


@pytest.mark.asyncio
async def test_build_falls_back_when_llm_fails(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("llm down")

    monkeypatch.setattr("app.agents.question_plan.structured_completion", boom)
    slots = await build_question_plan(BRIEF, 8, allow_llm=True)
    assert len(slots) == 8
    assert all("objective" in s and "topic" in s for s in slots)


@pytest.mark.asyncio
async def test_build_skips_llm_by_default(monkeypatch):
    calls = {"n": 0}

    async def spy(*_a, **_k):
        calls["n"] += 1
        raise RuntimeError("should not be called")

    monkeypatch.setattr("app.agents.question_plan.structured_completion", spy)
    slots = await build_question_plan(BRIEF, 8)
    assert calls["n"] == 0
    assert len(slots) == 8


def test_opening_from_bank_skips_llm():
    from app.services.interview_service import _opening_from_question_bank

    brief = {
        "question_areas": [{"topic": "Arrays", "guidance": "basics"}],
        "question_bank": [
            {
                "area": "Arrays",
                "question": "Why is index-based random access O(1) in an array?",
                "type": "conceptual",
            }
        ],
    }
    plan = deterministic_question_plan(brief, 3)
    decision = _opening_from_question_bank(
        brief, plan=plan, session_id="sess-1", mode="strict", history=[]
    )
    assert decision is not None
    assert "array" in decision.next_question.lower()
    assert decision.question_area
    assert decision.evaluation.coverage == "none"


@pytest.mark.asyncio
async def test_decide_includes_plan_slot(monkeypatch):
    from app.services import interview_service as svc

    plan = deterministic_question_plan(BRIEF, 15)
    session = SimpleNamespace(
        id=uuid.uuid4(),
        mode="strict",
        question_plan=plan,
    )
    captured: dict = {}

    async def fake_ainvoke(state):
        captured["payload"] = state["payload"]
        return {
            "decision": TurnDecision.model_validate(
                {
                    "evaluation": {
                        "coverage": "none",
                        "strengths": [],
                        "gaps": [],
                    },
                    "decision": "next_area",
                    "next_question": "Explain array random access.",
                    "question_area": "Array Basics",
                }
            ).model_dump()
        }

    monkeypatch.setattr(
        svc,
        "_graph",
        lambda: SimpleNamespace(ainvoke=fake_ainvoke),
    )
    monkeypatch.setattr(svc, "_turns", AsyncMock(return_value=[]))

    decision = await svc._decide(
        db=SimpleNamespace(),
        session=session,
        brief_content=BRIEF,
        last_answer=None,
    )
    assert decision.next_question
    assert "question_plan_slot" in captured["payload"]
    assert captured["payload"]["question_plan_slot"] == plan[0]
    assert "Ask about this objective" in captured["payload"]["diversity_instruction"]


@pytest.mark.asyncio
async def test_decide_null_plan_behaves_as_today(monkeypatch):
    from app.services import interview_service as svc

    session = SimpleNamespace(
        id=uuid.uuid4(),
        mode="strict",
        question_plan=None,
    )
    captured: dict = {}

    async def fake_ainvoke(state):
        captured["payload"] = state["payload"]
        return {
            "decision": TurnDecision.model_validate(
                {
                    "evaluation": {
                        "coverage": "none",
                        "strengths": [],
                        "gaps": [],
                    },
                    "decision": "next_area",
                    "next_question": "What is a hashmap?",
                    "question_area": "Hash Maps",
                }
            ).model_dump()
        }

    monkeypatch.setattr(
        svc,
        "_graph",
        lambda: SimpleNamespace(ainvoke=fake_ainvoke),
    )
    monkeypatch.setattr(svc, "_turns", AsyncMock(return_value=[]))

    await svc._decide(
        db=SimpleNamespace(),
        session=session,
        brief_content=BRIEF,
        last_answer=None,
    )
    assert "question_plan_slot" not in captured["payload"]
    assert "Ask about this objective" not in captured["payload"]["diversity_instruction"]


@pytest.mark.asyncio
async def test_autouse_fixture_noops_publish(monkeypatch):
    """Default conftest fixture replaces both publish import paths."""
    import app.services.events as events
    import app.services.interview_service as interview_service

    # Calling the (mocked) publishers must not raise and must not hit NATS.
    await interview_service.publish_feedback_job(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    await events.publish_feedback_job(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
