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


@pytest.mark.asyncio
async def test_build_falls_back_when_llm_fails(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(
        "app.agents.question_plan.structured_completion", boom
    )
    slots = await build_question_plan(BRIEF, 8)
    assert len(slots) == 8
    assert all("objective" in s and "topic" in s for s in slots)


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
    await interview_service.publish_feedback_job(
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    )
    await events.publish_feedback_job(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
