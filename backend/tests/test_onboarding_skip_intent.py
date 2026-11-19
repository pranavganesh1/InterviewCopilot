"""Isolated: explicit skip / move-on must change topic without a skill menu."""

from __future__ import annotations

from app.agents.onboarding import (
    decide_conversational_action,
    is_negative_or_skip,
    render_coach_action_reply,
    skip_move_on_reply,
    suggested_next_topics,
    wants_stop_session,
    wants_topic_switch,
)


VAULT = [
    {"category": "skill", "title": "DBMS", "details": {}},
    {"category": "skill", "title": "Java", "details": {}},
    {"category": "skill", "title": "SQL", "details": {}},
    {"category": "skill", "title": "Python", "details": {}},
    {
        "category": "internship",
        "title": "Velcontech Solutions",
        "details": {"role": "intern"},
    },
    {"category": "project", "title": "Campus Nav", "details": {}},
]

LOCKED = {
    "current_topic": "DBMS",
    "focus_kind": "skill",
    "focus_locked": True,
    "last_question_intent": "explore",
    "last_assistant_question": "How have you used DBMS in a real task?",
    "answers_received": [],
    "uncertainty_streak": 0,
    "skipped_categories": [],
}


def test_compound_move_next_changes_topic():
    msg = "I don't know, we can move next."
    assert is_negative_or_skip(msg) is True
    assert wants_topic_switch(msg) is True
    d = decide_conversational_action(msg, coach_context=LOCKED)
    assert d["action"] == "change_topic"


def test_bare_uncertainty_simplifies_not_skip():
    d = decide_conversational_action("I don't know.", coach_context=LOCKED)
    assert d["action"] == "simplify"


def test_skip_phrases_recognized():
    for msg in (
        "Skip this.",
        "Ask me something else.",
        "I don't have experience with that.",
        "Let's come back later.",
        "Next topic please",
    ):
        assert is_negative_or_skip(msg), msg
        action = decide_conversational_action(msg, coach_context=LOCKED)["action"]
        assert action in {"change_topic", "simplify", "pause"}, (msg, action)


def test_stop_intent():
    assert wants_stop_session("Let's stop here for now.") is True
    assert decide_conversational_action(
        "I want to stop.", coach_context=LOCKED
    )["action"] == "pause"
    assert wants_stop_session("Tell me more about DBMS") is False


def test_go_deeper_is_not_skip():
    assert is_negative_or_skip("I know this topic, let's go deeper.") is False
    action = decide_conversational_action(
        "I know this topic, let's go deeper.", coach_context=LOCKED
    )["action"]
    assert action in {"advance", "follow_up"}


def test_skip_reply_prefers_internship_not_skill_menu():
    reply = skip_move_on_reply(LOCKED, VAULT)
    assert "Which skill" not in reply
    assert "Java, SQL" not in reply
    assert "Velcontech" in reply or "Campus Nav" in reply


def test_change_topic_render_has_no_skill_menu():
    reply = render_coach_action_reply(
        "change_topic", coach_context=LOCKED, vault_summary=VAULT
    )
    assert "Which skill" not in reply
    assert "SQL or React" not in reply


def test_suggested_next_excludes_skipped_and_prefers_experience():
    rows = suggested_next_topics(
        VAULT, "DBMS", exclude_titles=["DBMS"], limit=3
    )
    assert rows
    assert rows[0]["kind"] in {"internship", "project", "education", "achievement"}
    assert all(r["title"] != "DBMS" for r in rows)
