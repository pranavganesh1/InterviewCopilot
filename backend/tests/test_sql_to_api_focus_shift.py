"""Isolated: SQL clarify must not revive after candidate moves to APIs.

No database access — decision + focus-shift helpers only.
"""

from __future__ import annotations

from app.agents.onboarding import (
    decide_conversational_action,
    extract_focus_shift_from_reply,
    render_coach_action_reply,
)
from app.gateway.llm import LLMCause, LLMGatewayError, gateway_http_status


SQL_LOCK = {
    "current_topic": "SQL",
    "focus_kind": "skill",
    "focus_locked": True,
    "last_question_intent": "detail",
    "last_assistant_question": (
        "Could you add one concrete detail about SQL — a tool, a task, or an outcome?"
    ),
    "answers_received": ["used joins once"],
    "uncertainty_streak": 0,
    "clarify_count": 1,
    "skipped_categories": [],
    "asked_questions": [
        "could you add one concrete detail about sql a tool a task or an outcome"
    ],
}

API_CHOICE_Q = (
    "You'd like to move the focus to APIs. Would you prefer to practice "
    "building a RESTful endpoint for your music database, or consuming an "
    "external API from a client app?"
)


def test_idk_go_to_api_advances_not_simplify():
    d = decide_conversational_action(
        "I don't know, we will go to API.",
        coach_context=SQL_LOCK,
    )
    assert d["action"] == "advance"
    assert d["reason"] == "subject_shift"


def test_external_api_selection_does_not_clarify_sql():
    ctx = {
        **SQL_LOCK,
        # Stale lock still SQL, but last ask already pivoted to APIs.
        "last_assistant_question": API_CHOICE_Q,
        "last_question_intent": "explore",
    }
    d = decide_conversational_action("External API.", coach_context=ctx)
    assert d["action"] == "advance"
    assert d["reason"] in {"selection_or_pivoted_ask", "default_continue"}
    out = render_coach_action_reply(d["action"], coach_context=ctx)
    assert "concrete detail about SQL" not in out


def test_focus_shift_extracts_apis_from_pivot_reply():
    shifted = extract_focus_shift_from_reply(API_CHOICE_Q, "SQL")
    assert shifted is not None
    assert "api" in shifted.lower()


def test_second_brief_answer_does_not_reclarify_same_topic():
    """Clarify at most once — second brief reply advances instead of looping."""
    d = decide_conversational_action("idk", coach_context=SQL_LOCK)
    # Last ask is still the SQL clarify and targets SQL → uncertainty simplifies
    # OR if treated as brief after clarify_count, advance.
    assert d["action"] in {"simplify", "advance", "change_topic"}
    assert d["action"] != "clarify"


def test_brief_on_same_topic_clarifies_only_when_not_yet_asked():
    ctx = {
        **SQL_LOCK,
        "clarify_count": 0,
        "asked_questions": [],
        "last_assistant_question": (
            "How have you used SQL in a real task or project, and what was the outcome?"
        ),
        "last_question_intent": "explore",
        "answers_received": ["a bit"],
    }
    d = decide_conversational_action("not sure", coach_context=ctx)
    # "not sure" is uncertainty → simplify on locked topic
    assert d["action"] == "simplify"

    d2 = decide_conversational_action("ok", coach_context=ctx)
    # "ok" is too short for open ask → clarify once
    assert d2["action"] == "clarify"


def test_gateway_http_status_maps_causes():
    assert (
        gateway_http_status(LLMGatewayError("x", cause=LLMCause.rate_limited)) == 429
    )
    assert (
        gateway_http_status(LLMGatewayError("x", cause=LLMCause.schema_rejected))
        == 422
    )
    assert gateway_http_status(LLMGatewayError("x", cause=LLMCause.timeout)) == 504
    assert gateway_http_status(LLMGatewayError("x", cause=LLMCause.overloaded)) == 503
