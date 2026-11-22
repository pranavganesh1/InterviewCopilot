"""Isolated: contextual conversational decisions (coach + interview policy).

Asserts decision quality and mode behaviour — not exact reply strings.
"""

from __future__ import annotations

from app.agents.interviewer import (
    AnswerEvaluation,
    TurnDecision,
    apply_local_policy,
    classify_answer_outcome,
)
from app.agents.onboarding import (
    decide_conversational_action,
    render_coach_action_reply,
    wants_stop_session,
)

JAVA_CTX = {
    "current_topic": "Java",
    "focus_kind": "skill",
    "focus_locked": True,
    "last_question_intent": "explore",
    "last_assistant_question": (
        "Let's dig into your Java experience. How have you used it in a real task or project?"
    ),
    "answers_received": [],
    "uncertainty_streak": 0,
    "skipped_categories": [],
}

VAULT = [
    {"category": "skill", "title": "Java", "details": {}},
    {"category": "skill", "title": "SQL", "details": {}},
    {"category": "skill", "title": "React", "details": {}},
    {
        "category": "internship",
        "title": "Velcontech Solutions",
        "details": {"role": "intern"},
    },
]


def _decision(**kwargs) -> TurnDecision:
    ev = kwargs.pop(
        "evaluation",
        {"coverage": "none", "strengths": [], "gaps": []},
    )
    if isinstance(ev, dict):
        ev = AnswerEvaluation(**ev)
    return TurnDecision(
        evaluation=ev,
        decision=kwargs.get("decision", "next_area"),
        next_question=kwargs.get(
            "next_question",
            "Would you like to switch to another skill like SQL or React, "
            "or dive into one of your projects?",
        ),
        question_area=kwargs.get("question_area", "Java"),
        evaluator_checks=kwargs.get("evaluator_checks", []),
        notes_for_report=kwargs.get("notes_for_report", ""),
    )


def test_uncertainty_on_example_simplifies_same_topic():
    d = decide_conversational_action("I don't know.", coach_context=JAVA_CTX)
    assert d["action"] == "simplify"
    reply = render_coach_action_reply(d["action"], coach_context=JAVA_CTX, vault_summary=VAULT)
    low = reply.lower()
    assert "java" in low
    assert "which skill" not in low
    assert "sql" not in low or "java" in low  # may mention Java only
    assert "would you like to switch" not in low
    assert "react" not in low


def test_not_understanding_question_simplifies():
    d = decide_conversational_action("I don't understand the question.", coach_context=JAVA_CTX)
    assert d["action"] == "simplify"


def test_explicit_topic_change():
    d = decide_conversational_action("Ask me something else.", coach_context=JAVA_CTX)
    assert d["action"] == "change_topic"
    reply = render_coach_action_reply(d["action"], coach_context=JAVA_CTX, vault_summary=VAULT)
    assert "which skill" not in reply.lower()
    assert "Java, SQL" not in reply


def test_hint_request_guided_vs_strict():
    guided = decide_conversational_action(
        "Can you give me a hint?", coach_context=JAVA_CTX, mode="guided"
    )
    strict = decide_conversational_action(
        "Can you give me a hint?", coach_context=JAVA_CTX, mode="strict"
    )
    assert guided["action"] == "guide"
    assert strict["action"] == "simplify"
    guided_reply = render_coach_action_reply(
        "guide", coach_context=JAVA_CTX, vault_summary=VAULT, mode="guided"
    )
    strict_reply = render_coach_action_reply(
        "simplify", coach_context=JAVA_CTX, vault_summary=VAULT, mode="strict"
    )
    # Strict must not hand a worked answer / spoiler ladder.
    assert "the answer is" not in strict_reply.lower()
    assert "nudge" in guided_reply.lower() or "situation" in guided_reply.lower()


def test_partial_answer_follow_up():
    d = decide_conversational_action(
        "I used Java a bit in college labs.",
        coach_context=JAVA_CTX,
    )
    assert d["action"] == "follow_up"


def test_detailed_answer_advances():
    msg = (
        "In my internship I used Java with Spring Boot to build a REST API "
        "because we needed authentication for internal tools, for example "
        "JWT filters, and we built integration tests around the login flow."
    )
    d = decide_conversational_action(msg, coach_context=JAVA_CTX)
    assert d["action"] == "advance"


def test_unexpected_subject_shift():
    d = decide_conversational_action(
        "Actually, can we talk about my internship instead?",
        coach_context=JAVA_CTX,
    )
    assert d["action"] == "change_topic"


def test_contradiction_still_contextual_not_menu():
    """Earlier they claimed Java; now they deny experience — change topic, no menu."""
    ctx = {**JAVA_CTX, "answers_received": ["I am strong in Java"]}
    d = decide_conversational_action(
        "I don't have experience with that.",
        coach_context=ctx,
    )
    assert d["action"] == "change_topic"
    reply = render_coach_action_reply(d["action"], coach_context=ctx, vault_summary=VAULT)
    assert "which skill" not in reply.lower()


def test_repeated_uncertainty_changes_topic():
    ctx = {**JAVA_CTX, "uncertainty_streak": 2}
    d = decide_conversational_action("I'm not sure.", coach_context=ctx)
    assert d["action"] == "change_topic"


def test_pause_intent():
    assert wants_stop_session("Let's stop here.") is True
    d = decide_conversational_action("Let's stop here.", coach_context=JAVA_CTX)
    assert d["action"] == "pause"


def test_interview_idk_not_scored_incorrect():
    assert (
        classify_answer_outcome("none", answer_text="idk", checks=["idk_answer"])
        == "Unclear or insufficient information"
    )


def test_interview_first_idk_simplifies_not_skill_menu():
    fixed = apply_local_policy(
        _decision(
            decision="next_area",
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            evaluator_checks=["idk_answer"],
            next_question=(
                "You're not sure about a specific Java example. "
                "Would you like to switch to another skill like SQL or React, "
                "or dive into one of your projects?"
            ),
        ),
        {
            "mode": "strict",
            "turns_in_current_area": 1,
            "current_area": "Java",
            "remaining_areas": ["SQL", "React"],
            "last_answer": "I don't know.",
            "questions_remaining": 8,
        },
    )
    assert fixed.decision == "follow_up"
    assert fixed.question_area == "Java"
    low = (fixed.next_question or "").lower()
    assert "would you like to switch" not in low
    assert "sql or react" not in low
    assert "java" in low


def test_interview_guided_idk_softens_without_spoilers():
    fixed = apply_local_policy(
        _decision(
            decision="follow_up",
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            evaluator_checks=["idk_answer"],
            next_question="The answer is polymorphism. What is inheritance?",
        ),
        {
            "mode": "guided",
            "turns_in_current_area": 1,
            "current_area": "OOP",
            "remaining_areas": ["DBMS"],
            "last_answer": "idk",
            "questions_remaining": 8,
        },
    )
    assert fixed.decision == "follow_up"
    assert fixed.question_area == "OOP"
    assert "the answer is" not in (fixed.next_question or "").lower()


def test_interview_second_weak_moves_on():
    fixed = apply_local_policy(
        _decision(
            decision="follow_up",
            evaluation={"coverage": "none", "strengths": [], "gaps": ["still unsure"]},
            evaluator_checks=["idk_answer"],
        ),
        {
            "mode": "strict",
            "turns_in_current_area": 2,
            "current_area": "Java",
            "remaining_areas": ["SQL"],
            "last_answer": "I still don't know",
            "questions_remaining": 7,
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "SQL"
