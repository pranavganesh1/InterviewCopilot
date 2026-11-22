"""Step 4 — Adaptive Interview Intelligence (isolated / offline)."""

from types import SimpleNamespace

import pytest

from app.agents.interviewer import (
    CLOSING_MESSAGE,
    TurnDecision,
    apply_local_policy,
    classify_answer_outcome,
    evaluate_answer_with_meta,
    system_prompt_for_mode,
)
from app.agents.question_dedupe import (
    is_duplicate_question,
    revisit_justified,
    same_concept_asked,
)
from app.agents.question_plan import (
    DEFAULT_QUESTIONS_PER_TOPIC,
    _blocked_topic_sequence,
    _questions_per_topic,
)
from app.services.weakness import (
    apply_plan_difficulty_nudge,
    difficulty_nudge_for_coverage,
    gradual_difficulty,
)


def _decision(**overrides):
    base = {
        "evaluation": {"coverage": "partial", "strengths": [], "gaps": ["missing detail"]},
        "decision": "next_area",
        "next_question": "Explain one related concept briefly.",
        "question_area": "Python",
        "notes_for_report": "ok",
    }
    base.update(overrides)
    return TurnDecision.model_validate(base)


def test_classify_answer_outcomes():
    assert classify_answer_outcome("excellent") == "Correct"
    assert classify_answer_outcome("good") == "Correct"
    assert classify_answer_outcome("partial") == "Partially correct"
    assert classify_answer_outcome("none") == "Incorrect"
    assert (
        classify_answer_outcome(
            "partial",
            answer_text="ok",
            checks=["too_short_answer", "brief_unclear"],
        )
        == "Unclear or insufficient information"
    )
    assert (
        classify_answer_outcome("none", answer_text="", checks=["empty_answer"])
        == "Unclear or insufficient information"
    )
    assert (
        classify_answer_outcome("none", answer_text="idk", checks=["idk_answer"])
        == "Unclear or insufficient information"
    )


@pytest.mark.asyncio
async def test_short_answer_is_unclear_not_incorrect(monkeypatch):
    async def boom(*_a, **_k):
        raise AssertionError("LLM must not run for short answers")

    monkeypatch.setattr("app.agents.interviewer.structured_completion", boom)
    ev, checks = await evaluate_answer_with_meta(
        {"last_answer": "ok", "last_question": "What is a mutex?", "mode": "strict"}
    )
    assert ev.coverage == "partial"
    assert "too_short_answer" in checks
    assert "brief_unclear" in checks
    assert classify_answer_outcome(ev.coverage, answer_text="ok", checks=checks) == (
        "Unclear or insufficient information"
    )


def test_correct_answer_advances():
    fixed = apply_local_policy(
        _decision(
            decision="follow_up",
            evaluation={"coverage": "excellent", "strengths": ["clear"], "gaps": []},
            next_question="Why does GIL matter?",
        ),
        {
            "turns_in_current_area": 1,
            "current_area": "Python",
            "remaining_areas": ["SQL"],
            "last_answer": "A detailed correct explanation of iterators.",
            "questions_remaining": 10,
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "SQL"


def test_partial_triggers_follow_up_with_gap_note():
    fixed = apply_local_policy(
        _decision(
            decision="next_area",
            question_area="SQL",
            evaluation={
                "coverage": "partial",
                "strengths": ["named JOIN"],
                "gaps": ["Did not explain INNER vs LEFT"],
            },
        ),
        {
            "turns_in_current_area": 1,
            "current_area": "Python",
            "remaining_areas": ["SQL"],
            "last_answer": "Joins combine tables",
            "questions_remaining": 10,
        },
    )
    assert fixed.decision == "follow_up"
    assert fixed.question_area == "Python"
    assert "INNER vs LEFT" in (fixed.notes_for_report or "")


def test_incorrect_gets_follow_up_then_cap_moves_on():
    first = apply_local_policy(
        _decision(
            decision="next_area",
            evaluation={"coverage": "none", "strengths": [], "gaps": ["wrong definition"]},
        ),
        {
            "turns_in_current_area": 1,
            "current_area": "DBMS",
            "remaining_areas": ["OS"],
            "last_answer": "A database is just Excel",
            "questions_remaining": 8,
        },
    )
    assert first.decision == "follow_up"

    capped = apply_local_policy(
        _decision(
            decision="follow_up",
            evaluation={"coverage": "none", "strengths": [], "gaps": ["still wrong"]},
        ),
        {
            "turns_in_current_area": 2,
            "current_area": "DBMS",
            "remaining_areas": ["OS"],
            "last_answer": "Still unsure",
            "questions_remaining": 7,
        },
    )
    assert capped.decision == "next_area"
    assert capped.question_area == "OS"


def test_follow_up_limit_respected():
    fixed = apply_local_policy(
        _decision(decision="follow_up"),
        {
            "turns_in_current_area": 2,
            "current_area": "OS",
            "remaining_areas": ["Networks"],
            "questions_remaining": 5,
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "Networks"


def test_topic_block_of_three_when_configured():
    assert DEFAULT_QUESTIONS_PER_TOPIC == 3
    assert _questions_per_topic(15, 5, duration_minutes=60) == 3
    seq = _blocked_topic_sequence(
        ["Python", "SQL", "DBMS", "OS", "DSA"], 15, duration_minutes=60
    )
    assert seq[:3] == ["Python", "Python", "Python"]
    assert seq[3:6] == ["SQL", "SQL", "SQL"]


def test_topic_budget_advances_after_block():
    fixed = apply_local_policy(
        _decision(decision="next_area", question_area="Python"),
        {
            "turns_in_current_area": 3,
            "current_area": "Python",
            "topic_budget": 3,
            "remaining_areas": ["SQL"],
            "question_plan_slot": {"topic": "SQL", "objective": "joins"},
            "questions_remaining": 9,
            "last_answer": "list comprehensions and generators",
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "SQL"


def test_duration_closing_when_time_low():
    fixed = apply_local_policy(
        _decision(decision="next_area", next_question="What is a process?"),
        {
            "turns_in_current_area": 1,
            "current_area": "OS",
            "remaining_areas": ["Networks"],
            "questions_remaining": 8,
            "minutes_remaining": 4,
            "last_answer": "A process is a running program with its own address space.",
        },
    )
    assert fixed.decision == "complete"
    assert fixed.next_question == CLOSING_MESSAGE
    assert "?" not in fixed.next_question


def test_questions_remaining_zero_closes():
    fixed = apply_local_policy(
        _decision(decision="next_area", next_question="Another question?"),
        {"questions_remaining": 0, "last_answer": "done"},
    )
    assert fixed.decision == "complete"
    assert fixed.next_question == CLOSING_MESSAGE


def test_difficulty_adapts_gradually():
    assert difficulty_nudge_for_coverage("excellent") == "advanced"
    assert gradual_difficulty("foundational", "advanced") == "intermediate"
    assert gradual_difficulty("advanced", "foundational") == "intermediate"
    assert gradual_difficulty("intermediate", "intermediate") is None

    plan = [
        {"topic": "Accounting", "difficulty": "foundational"},
        {"topic": "Finance", "difficulty": "foundational"},
    ]
    assert apply_plan_difficulty_nudge(plan, questions_asked=1, coverage="excellent")
    assert plan[1]["difficulty"] == "intermediate"

    plan2 = [
        {"topic": "OS", "difficulty": "advanced"},
        {"topic": "DBMS", "difficulty": "advanced"},
    ]
    assert apply_plan_difficulty_nudge(plan2, questions_asked=1, coverage="none")
    assert plan2[1]["difficulty"] == "intermediate"


def test_strict_vs_guided_mode_preserved():
    strict = system_prompt_for_mode("strict").lower()
    guided = system_prompt_for_mode("guided").lower()
    assert "never" in strict and "hint" in strict
    assert "assistance" in guided or "hint" in guided

    praised = _decision(
        next_question="Great job! The answer is B-trees. What is indexing?",
        decision="next_area",
        evaluation={"coverage": "good", "strengths": ["ok"], "gaps": []},
    )
    strict_d = apply_local_policy(
        praised,
        {
            "mode": "strict",
            "turns_in_current_area": 1,
            "current_area": "DBMS",
            "remaining_areas": ["OS"],
            "last_answer": "indexes speed lookups",
            "questions_remaining": 9,
        },
    )
    guided_d = apply_local_policy(
        praised,
        {
            "mode": "guided",
            "turns_in_current_area": 1,
            "current_area": "DBMS",
            "remaining_areas": ["OS"],
            "last_answer": "indexes speed lookups",
            "questions_remaining": 9,
        },
    )
    assert "great job" not in (strict_d.next_question or "").lower()
    assert "the answer is" not in (strict_d.next_question or "").lower()
    assert strict_d.decision == "next_area"
    assert guided_d.decision == "next_area"


def test_project_defense_prefers_selected_project():
    fixed = apply_local_policy(
        _decision(
            decision="follow_up",
            evaluation={"coverage": "good", "strengths": ["ok"], "gaps": []},
            question_area="QCGNN",
        ),
        {
            "turns_in_current_area": 1,
            "current_area": "QCGNN",
            "remaining_areas": ["Music Database Management System", "OS"],
            "last_answer": "We used a hybrid classical-quantum pipeline.",
            "questions_remaining": 8,
            "defense_mode": True,
            "candidate_prep_context": {
                "selected_projects": ["Music Database Management System"]
            },
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "Music Database Management System"


def test_no_arbitrary_project_when_none_selected():
    fixed = apply_local_policy(
        _decision(
            decision="follow_up",
            evaluation={"coverage": "excellent", "strengths": ["ok"], "gaps": []},
        ),
        {
            "turns_in_current_area": 1,
            "current_area": "Python",
            "remaining_areas": ["SQL", "Made-Up Project"],
            "last_answer": "Generators yield values lazily.",
            "questions_remaining": 8,
            "defense_mode": True,
            "candidate_prep_context": {"selected_projects": []},
        },
    )
    assert fixed.question_area == "SQL"


def test_behavioral_preferred_format_honored():
    fixed = apply_local_policy(
        _decision(
            decision="next_area",
            question_type="conceptual",
            evaluation={"coverage": "good", "strengths": ["ok"], "gaps": []},
            next_question="Tell me about a time you owned a production incident.",
            question_area="Leadership",
        ),
        {
            "mode": "strict",
            "turns_in_current_area": 1,
            "current_area": "Python",
            "remaining_areas": ["Leadership"],
            "preferred_format": "behavioral",
            "allowed_types": ["conceptual", "behavioral", "scenario"],
            "last_answer": "Detailed correct answer about Python GIL.",
            "questions_remaining": 6,
        },
    )
    assert fixed.question_type == "behavioral"


def test_duplicate_prevention_and_justified_revisit():
    asked = ["What is Newton's second law?"]
    assert is_duplicate_question("What is Newton's second law?", asked)
    assert not is_duplicate_question(
        "How does Newton's second law apply to circular motion?", asked
    )
    assert same_concept_asked(
        "Explain time complexity of hashmap lookup",
        ["What is the time complexity of hash map get?"],
    )
    assert revisit_justified(is_follow_up=True)
    assert revisit_justified(prior_coverage="partial")
    assert revisit_justified(difficulty_changed=True)
    assert not revisit_justified(prior_coverage="excellent")


def test_complete_does_not_keep_assessment_question():
    fixed = apply_local_policy(
        _decision(decision="complete", next_question="What else can you tell me?"),
        {"questions_remaining": 0},
    )
    assert fixed.decision == "complete"
    assert fixed.next_question == CLOSING_MESSAGE


def test_topic_coverage_does_not_linger_forever():
    """After topic_budget turns, leave even if LLM stays on the same area."""
    fixed = apply_local_policy(
        _decision(decision="next_area", question_area="Python"),
        {
            "turns_in_current_area": 4,
            "current_area": "Python",
            "topic_budget": 3,
            "remaining_areas": ["SQL"],
            "questions_remaining": 5,
            "last_answer": "enough depth on this topic already",
        },
    )
    assert fixed.question_area == "SQL"
