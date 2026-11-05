"""Task 10: interviewer mode routing, validation and repeat avoidance."""

import pytest
from pydantic import ValidationError

from app.agents.interviewer import (
    TurnDecision,
    apply_local_policy,
    decision_violation,
    system_prompt_for_mode,
)


def _decision(**overrides):
    base = {
        "evaluation": {"coverage": "partial", "strengths": [], "gaps": ["x"]},
        "decision": "follow_up",
        "next_question": "How do hash collisions work?",
        "question_area": "Hashmaps",
        "notes_for_report": "ok",
    }
    base.update(overrides)
    return TurnDecision.model_validate(base)


def test_mode_routing_keeps_strict_semantics():
    strict = system_prompt_for_mode("strict").lower()
    guided = system_prompt_for_mode("guided").lower()
    assert "never put hints" in strict or "never give hints" in strict
    assert "next_question" in strict
    assert "assistance" in guided


def test_output_validation_rejects_empty_question_when_not_complete():
    with pytest.raises(ValidationError):
        _decision(next_question="  ", decision="next_area")


def test_complete_allows_empty_question():
    d = _decision(decision="complete", next_question="")
    assert d.decision == "complete"


def test_follow_up_hard_limit_coerced_by_local_policy():
    d = _decision(decision="follow_up")
    fixed = apply_local_policy(d, {"turns_in_current_area": 2, "remaining_areas": ["Big-O"]})
    assert fixed.decision == "next_area"
    assert fixed.question_area == "Big-O"

    done = apply_local_policy(d, {"turns_in_current_area": 2, "remaining_areas": []})
    assert done.decision == "complete"


def test_repeat_question_detected():
    d = _decision(next_question="Explain hashmaps and collisions.")
    violation = decision_violation(
        d,
        {
            "turns_in_current_area": 1,
            "asked_questions": ["Explain hashmaps and collisions."],
        },
    )
    assert violation is not None
    assert "repeats" in violation


def test_distinct_question_allowed():
    d = _decision(next_question="What is Big-O of lookup?")
    assert (
        decision_violation(
            d,
            {
                "turns_in_current_area": 1,
                "asked_questions": ["Explain hashmaps and collisions."],
            },
        )
        is None
    )


@pytest.mark.asyncio
async def test_run_interviewer_turn_repairs_then_forces_unique(monkeypatch):
    from app.agents import interviewer as mod
    from app.agents.question_dedupe import is_duplicate_question

    calls: list[dict] = []

    async def fake_structured(client, *, system, user_payload, schema, **_k):
        calls.append(user_payload)
        # Always return a duplicate question so repairs keep failing.
        return TurnDecision.model_validate(
            {
                "evaluation": {"coverage": "none", "strengths": [], "gaps": []},
                "decision": "next_area",
                "next_question": "Same question",
                "question_area": "Hashmaps",
            }
        )

    monkeypatch.setattr(mod, "structured_completion", fake_structured)

    decision = await mod.run_interviewer_turn(
        payload={
            "mode": "strict",
            "asked_questions": ["Same question"],
            "turns_in_current_area": 0,
            "remaining_areas": ["Big-O"],
            "covered_areas": ["Hashmaps"],
            "questions_remaining": 10,
        }
    )
    # initial + 2 bounded repairs, then deterministic unique fallback
    assert len(calls) == 3
    assert all(c.get("mode") == "strict" for c in calls)
    assert not is_duplicate_question(decision.next_question, ["Same question"])
    assert decision.next_question.strip()
