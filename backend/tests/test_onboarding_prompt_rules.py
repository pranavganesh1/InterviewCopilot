"""Stubbed checks that onboarding prompts encode mentor-style conversation rules."""

from app.agents.onboarding import (
    GOALS_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    continue_topic_reply,
    sanitize_coach_reply,
    suggested_next_topics,
    topic_focus_reply,
)


def test_profile_prompt_avoids_yes_no_detail_loops():
    text = " ".join(SYSTEM_PROMPT.lower().split())
    assert "what / how / which" in text or "what, how, or which" in text
    assert "yes/no" in text
    assert "do not repeat the same ask" in text
    assert "skip" in text


def test_profile_prompt_requires_mentor_voice_not_vault_logging():
    text = " ".join(SYSTEM_PROMPT.lower().split())
    assert "react" in text and "reflect" in text
    assert "got it" in text  # banned phrasing called out
    assert "i've added" in text or "never claim" in text
    assert "topic lock" in text or "focus_locked" in text
    assert "one question" in text
    assert "sufficiently explored" in text or "smooth" in text


def test_goals_prompt_still_present():
    goals = GOALS_SYSTEM_PROMPT.lower()
    assert "preparation coach" in goals or "goals" in goals
    assert "got it" in goals or "never claim" in goals


def test_sanitize_strips_persistence_claims():
    raw = (
        "Got it — thanks for the details. I've added the purpose, technologies, "
        "and SQL implementation notes to your project entry. "
        "How did you choose the schema?"
    )
    cleaned = sanitize_coach_reply(raw)
    assert "i've added" not in cleaned.lower()
    assert "project entry" not in cleaned.lower()
    assert "schema" in cleaned.lower()
    assert cleaned.startswith("How") or "How" in cleaned


def test_topic_replies_sound_human_not_mechanical():
    item = {
        "title": "Music Database Management",
        "kind": "project",
        "details": {"purpose": "store songs", "technologies": "MySQL"},
    }
    reply = topic_focus_reply(item)
    assert "Music Database Management" in reply
    assert "I've added" not in reply
    assert "?" in reply

    cont = continue_topic_reply(
        {
            "current_topic": "Music Database Management",
            "focus_kind": "project",
            "answers_received": ["a", "b", "c"],
        },
        [
            item,
            {"category": "skill", "title": "Python", "details": {}},
        ],
    )
    assert cont
    assert "Python" in cont
    assert "Music Database Management" in cont
    assert "clearer picture" not in cont.lower()
    assert not cont.lower().startswith("nice")


def test_continue_topic_avoids_repeating_last_probe():
    ctx = {
        "current_topic": "Inventory Tracker",
        "focus_kind": "project",
        "answers_received": ["used postgres"],
        "asked_questions": [
            "staying with “inventory tracker” — what problem were you solving, "
            "and who was it for?"
        ],
        "last_assistant_question": (
            "Staying with “Inventory Tracker” — What problem were you solving, "
            "and who was it for?"
        ),
    }
    first = continue_topic_reply(ctx, [{"category": "project", "title": "Inventory Tracker", "details": {}}])
    second = continue_topic_reply(
        {**ctx, "answers_received": ["used postgres", "ok"]},
        [{"category": "project", "title": "Inventory Tracker", "details": {}}],
    )
    assert first and second
    assert first != second
    assert "clearer picture" not in first.lower()


def test_suggested_next_topics_skips_current():
    vault = [
        {"category": "project", "title": "A", "details": {}},
        {"category": "skill", "title": "Python", "details": {}},
    ]
    nxt = suggested_next_topics(vault, "A")
    assert nxt and nxt[0]["title"] == "Python"
