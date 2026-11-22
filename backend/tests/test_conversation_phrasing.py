"""Isolated multi-turn checks: no rote 'Let's dig into…' across topic switches."""

from __future__ import annotations

from app.agents.onboarding import (
    continue_topic_reply,
    sanitize_coach_reply,
    skip_move_on_reply,
    topic_focus_reply,
)

VAULT = [
    {"category": "skill", "title": "Java", "details": {}},
    {"category": "skill", "title": "SQL", "details": {}},
    {"category": "skill", "title": "React", "details": {}},
    {"category": "skill", "title": "DBMS", "details": {}},
    {
        "category": "project",
        "title": "Campus Nav",
        "details": {"purpose": "indoor routing", "technologies": "Arduino"},
    },
    {
        "category": "internship",
        "title": "Velcontech Solutions",
        "details": {"role": "intern"},
    },
]

ROTE_OPENERS = (
    "let's dig into",
    "let's explore",
    "let's move on to",
    "tell me about your experience with",
    "staying with",
    "continuing with",
)


def _assert_no_rote(text: str) -> None:
    low = text.lower()
    for phrase in ROTE_OPENERS:
        assert phrase not in low, f"rote phrase in reply: {phrase!r} -> {text!r}"


def test_skill_chain_java_sql_react_dbms_no_repeated_dig_into():
    replies: list[str] = []
    ctx: dict = {
        "current_topic": "",
        "focus_kind": "",
        "focus_locked": False,
        "answers_received": [],
        "asked_questions": [],
        "last_assistant_question": "",
    }
    for skill in ("Java", "SQL", "React", "DBMS"):
        item = {"title": skill, "kind": "skill", "category": "skill", "details": {}}
        reply = topic_focus_reply(item, coach_context=ctx)
        replies.append(reply)
        _assert_no_rote(reply)
        assert skill in reply
        assert "?" in reply
        ctx = {
            "current_topic": skill,
            "focus_kind": "skill",
            "focus_locked": True,
            "answers_received": list(ctx["answers_received"])
            + [f"I used {skill} in a college lab for a small assignment."],
            "asked_questions": list(ctx["asked_questions"]) + [reply.lower()],
            "last_assistant_question": reply,
        }

    # Consecutive skill opens must not share the old fixed lead pattern.
    assert all(not r.lower().startswith("let's dig into") for r in replies)
    # At least some turns should be direct questions (no prior-answer bridge).
    direct = [r for r in replies if not r.lower().startswith("you mentioned")]
    assert len(direct) >= 1
    # When a bridge appears, it must come from their words, not a stock intro.
    for r, skill in zip(replies[1:], ("SQL", "React", "DBMS"), strict=True):
        if r.lower().startswith("you mentioned"):
            assert "college lab" in r.lower() or "assignment" in r.lower()
            assert skill in r


def test_project_and_internship_focus_are_direct_questions():
    project = topic_focus_reply(
        {
            "title": "Campus Nav",
            "kind": "project",
            "details": {"purpose": "indoor routing", "technologies": "Arduino"},
        },
        coach_context={"current_topic": "", "answers_received": []},
    )
    intern = topic_focus_reply(
        {
            "title": "Velcontech Solutions",
            "kind": "internship",
            "details": {},
        },
        coach_context={
            "current_topic": "Campus Nav",
            "answers_received": ["We built indoor routing with IR sensors for campus buildings."],
            "last_assistant_question": project,
        },
    )
    _assert_no_rote(project)
    _assert_no_rote(intern)
    assert "Campus Nav" in project
    assert "Velcontech" in intern
    assert project.lower().startswith("what") or "purpose" in project.lower()


def test_continue_topic_multi_turn_avoids_staying_with_prefix():
    ctx = {
        "current_topic": "Java",
        "focus_kind": "skill",
        "focus_locked": True,
        "answers_received": [],
        "asked_questions": [],
        "last_assistant_question": "",
    }
    seen: list[str] = []
    for i in range(3):
        reply = continue_topic_reply(ctx, VAULT)
        assert reply
        _assert_no_rote(reply)
        assert "java" in reply.lower()
        assert not reply.lower().startswith("on java:")
        seen.append(reply)
        ctx = {
            **ctx,
            "answers_received": list(ctx["answers_received"]) + [f"detail {i}"],
            "asked_questions": list(ctx["asked_questions"]) + [reply.lower()],
            "last_assistant_question": reply,
        }
    assert len(set(seen)) >= 2


def test_skip_move_on_has_no_explore_lead_in():
    ctx = {
        "current_topic": "Java",
        "focus_kind": "skill",
        "skipped_categories": [],
    }
    reply = skip_move_on_reply(ctx, VAULT)
    _assert_no_rote(reply)
    assert "let's explore another area" not in reply.lower()
    assert "?" in reply


def test_sanitize_strips_leading_rote_intros():
    raw = "Let's dig into your SQL experience. How have you used it in a real task or project?"
    cleaned = sanitize_coach_reply(raw)
    assert "let's dig into" not in cleaned.lower()
    assert "how have you used" in cleaned.lower()
