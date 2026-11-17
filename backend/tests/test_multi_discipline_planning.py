"""Fix 7: multi-discipline planning, soft topic match, vault personalization, fallbacks.

Offline unit tests only — no shared database writes.
"""

from types import SimpleNamespace

import pytest

from app.agents.interviewer import (
    _fallback_stems_for_payload,
    _fallback_unique_question,
    _payload_is_programming,
    _should_use_array_concept_bank,
)
from app.agents.question_plan import deterministic_question_plan
from app.agents.question_quality import active_profile, format_for_slot
from app.agents.session_pool import (
    areas_soft_match,
    normalize_area_key,
    pick_pool_question,
)
from app.services.probe import personalize_from_vault, vault_plan_areas


def _science_profile(**overrides):
    body = {
        "category": "science",
        "uses_code": False,
        "uses_math": True,
        "risk_level": "standard",
        "style_hint": "Ask one science reasoning question.",
        "allowed_types": ["conceptual", "mcq", "numeric", "case_study"],
    }
    body.update(overrides)
    return body


def _business_profile(**overrides):
    body = {
        "category": "business",
        "uses_code": False,
        "uses_math": True,
        "risk_level": "standard",
        "style_hint": "Ask one business reasoning question.",
        "allowed_types": ["conceptual", "mcq", "case_study"],
    }
    body.update(overrides)
    return body


def _programming_profile(**overrides):
    body = {
        "category": "programming",
        "uses_code": True,
        "uses_math": True,
        "risk_level": "standard",
        "style_hint": "Ask about behavior or trade-offs.",
        "allowed_types": ["conceptual", "mcq", "code_read", "coding"],
    }
    body.update(overrides)
    return body


def test_biology_plan_avoids_dsa_topics_and_coding_formats():
    brief = {
        "summary": "Undergraduate biology interview",
        "subject": "Cell Biology",
        "domain_profile": _science_profile(),
        "question_areas": [
            {"topic": "Cell Biology", "guidance": "organelles"},
            {"topic": "Enzymes", "guidance": "catalysis"},
            {"topic": "Genetics", "guidance": "inheritance"},
        ],
        "competencies": [],
    }
    slots = deterministic_question_plan(brief, 12, duration_minutes=45)
    topics = {s["topic"] for s in slots}
    assert "Cell Biology" in topics
    assert "Enzymes" in topics
    assert "Data Structures and Algorithms" not in topics
    assert "Arrays" not in topics
    assert all(s["format"] != "coding" for s in slots)
    assert all(s["format"] != "code_read" for s in slots)


def test_finance_plan_avoids_programming_formats():
    brief = {
        "summary": "Corporate finance interview",
        "subject": "Finance",
        "domain_profile": _business_profile(),
        "question_areas": [
            {"topic": "Cash Flow Statements", "guidance": "operating cash"},
            {"topic": "Valuation", "guidance": "DCF"},
            {"topic": "Working Capital", "guidance": "liquidity"},
        ],
        "competencies": [],
    }
    slots = deterministic_question_plan(brief, 10, duration_minutes=45)
    assert "Cash Flow Statements" in {s["topic"] for s in slots}
    assert all(s["format"] not in {"coding", "code_read"} for s in slots)


def test_physics_plan_stays_on_physics_topics():
    brief = {
        "summary": "Undergraduate physics interview",
        "subject": "Physics",
        "domain_profile": _science_profile(style_hint="Ask one physics reasoning question."),
        "question_areas": [
            {"topic": "Classical Mechanics", "guidance": "Newton"},
            {"topic": "Electromagnetism", "guidance": "Maxwell"},
            {"topic": "Conservation of Energy", "guidance": "work-energy"},
        ],
        "competencies": [],
    }
    slots = deterministic_question_plan(brief, 9, duration_minutes=40)
    topics = {s["topic"] for s in slots}
    assert "Classical Mechanics" in topics
    assert "Conservation of Energy" in topics
    assert "Hash Maps" not in topics


def test_computer_science_plan_keeps_programming_formats():
    brief = {
        "summary": "DSA interview",
        "subject": "Data Structures",
        "domain_profile": _programming_profile(),
        "question_areas": [
            {"topic": "Arrays", "guidance": "memory"},
            {"topic": "Hash Maps", "guidance": "collisions"},
            {"topic": "Trees", "guidance": "traversal"},
        ],
        "competencies": [],
    }
    slots = deterministic_question_plan(brief, 15, duration_minutes=60)
    formats = {s["format"] for s in slots}
    assert "coding" in formats or "code_read" in formats
    assert "Arrays" in {s["topic"] for s in slots}


def test_topic_normalization_casing_and_whitespace():
    assert normalize_area_key("  Cash   Flow  ") == "cash flow"
    assert areas_soft_match("Cash Flow", "cash  flow")
    assert areas_soft_match("Classical Mechanics", "classical mechanics")
    assert areas_soft_match("Enzymes", "Enzymes — interview focus")


def test_soft_match_does_not_cross_career_tracks():
    assert not areas_soft_match("Cell Biology", "Data Structures")
    assert not areas_soft_match("Cash Flow Statements", "Arrays")
    assert not areas_soft_match("Classical Mechanics", "Hash Maps")
    assert not areas_soft_match("finance", "financial markets analysis")


def test_pool_soft_match_prefers_normalized_topic_without_crossing():
    entries = [
        {
            "area": "Cash Flow Statements",
            "difficulty": "foundational",
            "type": "conceptual",
            "question": "How would you read operating cash flow from a statement example?",
        },
        {
            "area": "Arrays",
            "difficulty": "foundational",
            "type": "conceptual",
            "question": "Why is index-based random access O(1) in an array example?",
        },
    ]
    picked = pick_pool_question(
        entries,
        seed="soft-match-seed",
        slot={
            "topic": "cash  flow statements",
            "difficulty": "foundational",
            "format": "conceptual",
        },
        asked=[],
        history=[],
        reuse=False,
    )
    assert picked is not None
    assert picked["area"] == "Cash Flow Statements"


def test_vault_topics_helper_and_personalization_flags():
    items = [
        SimpleNamespace(category="skill", title="Python", details={}),
        SimpleNamespace(category="project", title="Line Follower", details={}),
        SimpleNamespace(category="other", title="Ignored", details={}),
    ]
    areas = vault_plan_areas(items, limit=8)
    titles = [a["topic"] for a in areas]
    assert "Line Follower" in titles
    assert "Python" in titles
    assert "Ignored" not in titles

    assert personalize_from_vault({"use_resume": True}) is True
    assert personalize_from_vault({"include_vault_topics": True}) is True
    assert personalize_from_vault({"use_resume": False, "include_vault_topics": False}) is False
    assert personalize_from_vault({}) is False


def test_profile_first_overrides_programming_keyword_heuristics():
    # Brief text looks CS-ish, but domain_profile forbids code.
    brief = {
        "summary": "Python scripting for lab automation arrays",
        "subject": "Lab Methods",
        "domain_profile": _science_profile(),
        "question_areas": [{"topic": "Lab Automation", "guidance": "protocols"}],
        "competencies": [],
    }
    profile = active_profile(brief)
    assert profile is not None
    assert profile["uses_code"] is False
    fmt = format_for_slot(0, programming=True, profile=profile)
    assert fmt != "coding"
    assert fmt != "code_read"

    payload = {
        "programming_track": True,  # stale regex would say yes
        "domain_profile": profile,
    }
    assert _payload_is_programming(payload) is False


def test_non_cs_fallback_is_domain_safe_and_category_aware():
    bio = {
        "programming_track": False,
        "domain_profile": _science_profile(),
        "asked_questions": ["What is one foundational idea in Enzymes?"],
        "remaining_areas": [],
        "covered_areas": ["Enzymes"],
        "current_area": "Enzymes",
        "questions_remaining": 8,
    }
    assert _should_use_array_concept_bank(bio, "Enzymes") is False
    q, area = _fallback_unique_question(bio)
    assert area == "Enzymes"
    low = q.lower()
    assert "hash" not in low
    assert "array" not in low
    assert "leetcode" not in low
    assert "implement" not in low or "enzym" in low
    stems = _fallback_stems_for_payload(bio)
    assert any("scientific" in s or "evidence" in s or "lab" in s for s in stems)

    fin = {
        "programming_track": False,
        "domain_profile": _business_profile(),
        "asked_questions": ["What is one foundational idea in Cash Flow?"],
        "remaining_areas": [],
        "covered_areas": ["Cash Flow Statements"],
        "current_area": "Cash Flow Statements",
        "questions_remaining": 8,
    }
    q2, _ = _fallback_unique_question(fin)
    assert "hash table" not in q2.lower()
    assert "collision" not in q2.lower()
    business_stems = _fallback_stems_for_payload(fin)
    assert any("business" in s or "cash flow" in s for s in business_stems)


def test_cs_fallback_still_allows_array_bank():
    payload = {
        "programming_track": True,
        "domain_profile": _programming_profile(),
        "asked_questions": ["Can you explain what an array is?"],
        "remaining_areas": [],
        "covered_areas": ["Arrays"],
        "current_area": "Arrays",
        "questions_remaining": 10,
    }
    assert _should_use_array_concept_bank(payload, "Arrays") is True
    q, area = _fallback_unique_question(payload)
    assert area == "Arrays"
    assert any(
        marker in q.lower()
        for marker in ("array", "subarray", "pointer", "prefix", "binary search")
    )


@pytest.mark.parametrize(
    "planned,area,expect",
    [
        ("Hash Maps", "hash maps", True),
        ("Two Pointers", "two-pointers", True),
        ("Working Capital", "Liquidity Ratios", False),
    ],
)
def test_soft_match_parametrized(planned, area, expect):
    assert areas_soft_match(planned, area) is expect
