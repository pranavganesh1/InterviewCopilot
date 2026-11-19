"""Phase D Feature 1: Adaptive Knowledge Intelligence (offline / mocked)."""

from types import SimpleNamespace

import pytest

from app.agents.interviewer import TurnDecision, apply_local_policy, system_prompt_for_mode
from app.agents.question_dedupe import is_duplicate_question
from app.agents.question_quality import question_type_allowed
from app.services.interview_service import build_covered_so_far
from app.services.weakness import (
    apply_plan_difficulty_nudge,
    difficulty_nudge_for_coverage,
    prioritize_remaining_areas,
)


def _decision(**overrides):
    base = {
        "evaluation": {"coverage": "partial", "strengths": [], "gaps": ["missing detail"]},
        "decision": "next_area",
        "next_question": "Explain one related concept briefly.",
        "question_area": "Genetics",
        "notes_for_report": "ok",
    }
    base.update(overrides)
    return TurnDecision.model_validate(base)


def test_correct_answer_advances_instead_of_follow_up():
    d = _decision(
        decision="follow_up",
        evaluation={"coverage": "excellent", "strengths": ["clear"], "gaps": []},
    )
    fixed = apply_local_policy(
        d,
        {
            "turns_in_current_area": 1,
            "current_area": "Genetics",
            "remaining_areas": ["Cell biology"],
            "last_answer": "Mendelian inheritance with examples",
            "covered_so_far": {
                "knowledge_state": {"recent_coverage": ["good", "excellent"]}
            },
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "Cell biology"


def test_partial_answer_gets_targeted_follow_up():
    d = _decision(decision="next_area", question_area="Cell biology")
    fixed = apply_local_policy(
        d,
        {
            "turns_in_current_area": 1,
            "current_area": "Genetics",
            "remaining_areas": ["Physiology"],
            "last_answer": "something about genes",
            "questions_remaining": 10,
        },
    )
    assert fixed.decision == "follow_up"
    assert fixed.question_area == "Genetics"


def test_incorrect_answer_then_follow_up_cap_moves_to_prerequisite_area():
    d = _decision(
        decision="follow_up",
        evaluation={"coverage": "none", "strengths": [], "gaps": ["basics missing"]},
    )
    fixed = apply_local_policy(
        d,
        {
            "turns_in_current_area": 2,
            "current_area": "Electromagnetism",
            "remaining_areas": ["Mechanics", "Optics"],
            "last_answer": "I do not know",
            "questions_remaining": 8,
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "Mechanics"


def test_strong_streak_increases_difficulty_on_plan():
    assert difficulty_nudge_for_coverage("excellent") == "advanced"
    plan = [
        {"topic": "Accounting", "difficulty": "foundational"},
        {"topic": "Finance", "difficulty": "foundational"},
    ]
    # Gradual: foundational → intermediate (not a jump to advanced).
    assert apply_plan_difficulty_nudge(plan, questions_asked=1, coverage="excellent")
    assert plan[1]["difficulty"] == "intermediate"


def test_weak_coverage_lowers_next_slot_difficulty():
    plan = [
        {"topic": "OS", "difficulty": "advanced"},
        {"topic": "DBMS", "difficulty": "advanced"},
    ]
    # Gradual: advanced → intermediate (not a jump to foundational).
    assert apply_plan_difficulty_nudge(plan, questions_asked=1, coverage="none")
    assert plan[1]["difficulty"] == "intermediate"


def test_knowledge_gaps_prioritize_remaining_areas():
    remaining = ["Optics", "Thermodynamics", "Mechanics"]
    ordered = prioritize_remaining_areas(
        remaining, session_weak_areas=["Mechanics", "Thermodynamics"]
    )
    assert ordered[0] in ("Mechanics", "Thermodynamics")
    assert set(ordered) == set(remaining)


def test_no_unnecessary_repeat_follow_up():
    d = _decision(decision="follow_up")
    fixed = apply_local_policy(
        d,
        {
            "turns_in_current_area": 2,
            "current_area": "DBMS",
            "remaining_areas": ["OS"],
            "questions_remaining": 5,
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "OS"


def test_no_repeated_questions_via_dedupe():
    asked = ["What is Newton's second law?"]
    assert is_duplicate_question("What is Newton's second law?", asked)
    assert not is_duplicate_question(
        "How does Newton's second law apply to circular motion?", asked
    )


@pytest.mark.parametrize(
    "profile,forbidden",
    [
        (
            {
                "category": "science",
                "uses_code": False,
                "allowed_types": ["conceptual", "numeric", "scenario"],
            },
            "coding",
        ),
        (
            {
                "category": "business",
                "uses_code": False,
                "allowed_types": ["conceptual", "scenario", "mcq"],
            },
            "coding",
        ),
        (
            {
                "category": "science",
                "uses_code": False,
                "allowed_types": ["conceptual", "numeric"],
            },
            "coding",
        ),
    ],
)
def test_domain_safety_blocks_coding_for_non_cs(profile, forbidden):
    payload = {"domain_profile": profile, "allowed_types": profile["allowed_types"]}
    assert not question_type_allowed(forbidden, payload)
    assert question_type_allowed("conceptual", payload)


def test_strict_prompt_hides_hints_guided_keeps_assistance():
    strict = system_prompt_for_mode("strict").lower()
    guided = system_prompt_for_mode("guided").lower()
    assert "hint" in strict
    assert "never" in strict
    assert "assistance" in guided or "hint" in guided


def test_knowledge_state_persists_in_covered_so_far():
    turns = [
        SimpleNamespace(
            question_area="Genetics",
            question="What is a gene?",
            answer="unit of heredity",
            evaluation_coverage="good",
            evaluation_gaps=[],
        ),
        SimpleNamespace(
            question_area="Physiology",
            question="Describe osmosis",
            answer="water moves",
            evaluation_coverage="partial",
            evaluation_gaps=["missing concentration gradient"],
        ),
    ]
    plan = [
        {"topic": "Genetics", "objective": "gene definition", "difficulty": "foundational"},
        {"topic": "Physiology", "objective": "osmosis", "difficulty": "intermediate"},
        {"topic": "Cell biology", "objective": "organelles", "difficulty": "intermediate"},
    ]
    mem = build_covered_so_far(turns, plan=plan, questions_asked=2)
    ks = mem["knowledge_state"]
    assert "Genetics" in ks["demonstrated_strengths"]
    assert any(g["area"] == "Physiology" for g in ks["knowledge_gaps"])
    assert ks["recent_coverage"] == ["good", "partial"]
    assert ks["questions_assessed"] == 2
    assert mem["next_planned_objective"]["topic"] == "Cell biology"


def test_apply_local_policy_strips_strict_spoilers_only():
    praised = _decision(
        next_question="Great job! The answer is mitosis. What is meiosis?",
        decision="next_area",
        evaluation={"coverage": "good", "strengths": ["ok"], "gaps": []},
    )
    strict = apply_local_policy(
        praised,
        {
            "mode": "strict",
            "turns_in_current_area": 1,
            "current_area": "Cell biology",
            "remaining_areas": ["Genetics"],
            "last_answer": "division of cells",
            "questions_remaining": 9,
        },
    )
    guided = apply_local_policy(
        praised,
        {
            "mode": "guided",
            "turns_in_current_area": 1,
            "current_area": "Cell biology",
            "remaining_areas": ["Genetics"],
            "last_answer": "division of cells",
            "questions_remaining": 9,
        },
    )
    assert "great job" not in (strict.next_question or "").lower()
    # Guided may retain softer phrasing; both still advance on good coverage.
    assert strict.decision == "next_area"
    assert guided.decision == "next_area"
