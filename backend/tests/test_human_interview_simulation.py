"""Isolated human-interview simulations (scenarios A–J). No shared DB writes.

Tests real decision functions with mocked LLM / in-memory coach state.
"""

from __future__ import annotations

import pytest

from app.agents.assistance import next_assistance_level
from app.agents.interviewer import (
    AnswerEvaluation,
    TurnDecision,
    apply_local_policy,
    classify_answer_outcome,
    strip_strict_spoilers,
    system_prompt_for_mode,
)
from app.agents.onboarding import (
    decide_conversational_action,
    extract_focus_shift_from_reply,
    render_coach_action_reply,
    topic_focus_reply,
)
from app.agents.question_quality import strip_strict_praise
from app.services.feedback_report_builder import enrich_assessments_with_turns
from app.services.probe import defense_system_rules, merge_defense_question_areas


def _td(**kwargs) -> TurnDecision:
    ev = kwargs.pop("evaluation", {"coverage": "partial", "strengths": [], "gaps": ["gap"]})
    if isinstance(ev, dict):
        ev = AnswerEvaluation(**ev)
    return TurnDecision(
        evaluation=ev,
        decision=kwargs.get("decision", "follow_up"),
        next_question=kwargs.get("next_question", "What comes next?"),
        question_area=kwargs.get("question_area", "General"),
        question_type=kwargs.get("question_type", "conceptual"),
        notes_for_report=kwargs.get("notes_for_report", ""),
        evaluator_checks=kwargs.get("evaluator_checks", []),
    )


# --- Scenario A: multi-turn formal policy progression ---

def test_scenario_a_five_turn_policy_progression():
    """Detailed answer advances; partial gets one follow-up; second weak moves on."""
    area = "Music Database"
    remaining = ["Normalization", "SQL Joins", "APIs"]

    # Turn 1: partial → follow_up same area
    t1 = apply_local_policy(
        _td(
            decision="next_area",
            question_area="SQL Joins",
            evaluation={
                "coverage": "partial",
                "strengths": ["named tables"],
                "gaps": ["Did not explain FK relationships"],
            },
        ),
        {
            "turns_in_current_area": 1,
            "current_area": area,
            "remaining_areas": remaining,
            "last_answer": "I stored songs in tables",
            "questions_remaining": 10,
        },
    )
    assert t1.decision == "follow_up"
    assert t1.question_area == area

    # Turn 2: excellent → next_area
    t2 = apply_local_policy(
        _td(
            decision="follow_up",
            evaluation={
                "coverage": "excellent",
                "strengths": ["clear FK design"],
                "gaps": [],
            },
            next_question="Why normalize to 3NF?",
        ),
        {
            "turns_in_current_area": 1,
            "current_area": area,
            "remaining_areas": remaining,
            "last_answer": (
                "Because we needed referential integrity between albums and tracks, "
                "for example album_id as a foreign key, and we built indexes on title."
            ),
            "questions_remaining": 9,
            "covered_so_far": {
                "knowledge_state": {"recent_coverage": ["good", "excellent"]}
            },
        },
    )
    assert t2.decision == "next_area"

    # Turns 3–5: budget forces leave after depth
    t5 = apply_local_policy(
        _td(decision="follow_up", evaluation={"coverage": "good", "strengths": ["ok"], "gaps": []}),
        {
            "turns_in_current_area": 3,
            "current_area": area,
            "remaining_areas": ["SQL Joins"],
            "topic_budget": 3,
            "last_answer": "detailed enough",
            "questions_remaining": 6,
        },
    )
    assert t5.decision == "next_area"
    assert t5.question_area == "SQL Joins"


# --- Scenario B: topic change (coach) ---

def test_scenario_b_topic_change_and_short_replies():
    sql_lock = {
        "current_topic": "SQL",
        "focus_kind": "skill",
        "focus_locked": True,
        "last_question_intent": "detail",
        "last_assistant_question": (
            "Could you add one concrete detail about SQL — a tool, a task, or an outcome?"
        ),
        "answers_received": ["used it a little"],
        "uncertainty_streak": 0,
        "clarify_count": 1,
        "asked_questions": [],
        "skipped_categories": [],
    }

    d_switch = decide_conversational_action(
        "Let's discuss APIs instead.", coach_context=sql_lock
    )
    assert d_switch["action"] in {"advance", "change_topic"}

    api_q = (
        "You'd like to move the focus to APIs. Would you prefer to practice "
        "building a RESTful endpoint, or consuming an external API?"
    )
    shifted = extract_focus_shift_from_reply(api_q, "SQL")
    assert shifted and "api" in shifted.lower()

    after_pivot = {
        **sql_lock,
        "last_assistant_question": api_q,
        "last_question_intent": "explore",
    }
    for msg in ("API", "External API", "Let's move on.", "Skip this.", "I don't know."):
        d = decide_conversational_action(msg, coach_context=after_pivot)
        assert d["action"] != "clarify", msg
        if d["action"] in {"simplify", "guide", "clarify", "change_topic", "pause", "follow_up", "advance"}:
            out = render_coach_action_reply(d["action"], coach_context=after_pivot)
            assert "concrete detail about SQL" not in out, msg

    # Natural discuss phrasing must pivot (RC-B2 fix).
    d_hr = decide_conversational_action(
        "I want to discuss HR.", coach_context=after_pivot
    )
    assert d_hr["action"] in {"advance", "change_topic"}
    d_switch_hr = decide_conversational_action(
        "switch to HR", coach_context=after_pivot
    )
    assert d_switch_hr["action"] in {"advance", "change_topic"}


# --- Scenario C: IDK ---

@pytest.mark.asyncio
async def test_scenario_c_live_path_skips_llm_on_idk(monkeypatch):
    """RC-C1 fix: empty/IDK/short answers skip structured_completion."""
    from app.agents import interviewer as iv

    calls: list[str] = []

    async def _fake_sc(**kwargs):
        calls.append("llm")
        return _td(
            decision="next_area",
            evaluation={"coverage": "good", "strengths": ["fabricated"], "gaps": []},
            next_question="Would you like to switch to another skill?",
            question_area="Other",
        )

    monkeypatch.setattr(iv, "structured_completion", _fake_sc)
    out = await iv.run_interviewer_turn(
        payload={
            "mode": "strict",
            "last_answer": "I don't know.",
            "current_area": "DBMS",
            "remaining_areas": ["OS"],
            "turns_in_current_area": 1,
            "questions_remaining": 8,
            "asked_questions": ["What is a B+ tree?"],
        }
    )
    assert calls == [], "IDK must not invoke the LLM"
    assert "idk_answer" in (out.evaluator_checks or [])
    assert out.evaluation.coverage == "none"
    assert out.decision == "follow_up"
    assert "switch to another skill" not in (out.next_question or "").lower()


def test_scenario_c_idk_policy_strict_and_guided():
    for mode in ("strict", "guided"):
        fixed = apply_local_policy(
            _td(
                decision="next_area",
                evaluation={"coverage": "none", "strengths": [], "gaps": []},
                evaluator_checks=["idk_answer"],
                next_question=(
                    "Would you like to switch to another skill like SQL or React?"
                ),
            ),
            {
                "mode": mode,
                "turns_in_current_area": 1,
                "current_area": "DBMS",
                "remaining_areas": ["OS"],
                "last_answer": "I don't know.",
                "questions_remaining": 8,
            },
        )
        assert fixed.decision == "follow_up"
        assert fixed.question_area == "DBMS"
        assert "switch to another skill" not in (fixed.next_question or "").lower()
        assert classify_answer_outcome(
            "none", answer_text="idk", checks=["idk_answer"]
        ) == "Unclear or insufficient information"

    # Second weak → move on
    capped = apply_local_policy(
        _td(
            decision="follow_up",
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            evaluator_checks=["idk_answer"],
        ),
        {
            "mode": "strict",
            "turns_in_current_area": 2,
            "current_area": "DBMS",
            "remaining_areas": ["OS"],
            "last_answer": "still don't know",
            "questions_remaining": 7,
        },
    )
    assert capped.decision == "next_area"
    assert capped.question_area == "OS"


# --- Scenarios D–F: partial / detailed / ambiguous ---

def test_scenario_d_partial_triggers_one_focused_follow_up():
    fixed = apply_local_policy(
        _td(
            decision="next_area",
            question_area="Other",
            evaluation={
                "coverage": "partial",
                "strengths": ["mentioned JOIN"],
                "gaps": ["Did not explain INNER vs LEFT"],
            },
        ),
        {
            "turns_in_current_area": 1,
            "current_area": "SQL",
            "remaining_areas": ["APIs"],
            "last_answer": "Joins combine tables",
            "questions_remaining": 8,
        },
    )
    assert fixed.decision == "follow_up"
    assert fixed.question_area == "SQL"
    assert "INNER vs LEFT" in (fixed.notes_for_report or "")


def test_scenario_e_detailed_excellent_advances():
    fixed = apply_local_policy(
        _td(
            decision="follow_up",
            evaluation={
                "coverage": "excellent",
                "strengths": ["complete"],
                "gaps": [],
            },
            next_question="Same area again?",
        ),
        {
            "turns_in_current_area": 1,
            "current_area": "SQL",
            "remaining_areas": ["APIs"],
            "last_answer": "A" * 200,
            "questions_remaining": 8,
            "covered_so_far": {
                "knowledge_state": {"recent_coverage": ["good", "excellent"]}
            },
        },
    )
    assert fixed.decision == "next_area"
    assert fixed.question_area == "APIs"


def test_scenario_f_ambiguous_brief_is_partial_not_incorrect():
    outcome = classify_answer_outcome(
        "partial", answer_text="ok", checks=["too_short_answer", "brief_unclear"]
    )
    assert outcome == "Unclear or insufficient information"
    # Coach: second clarify blocked
    ctx = {
        "current_topic": "SQL",
        "focus_kind": "skill",
        "focus_locked": True,
        "last_question_intent": "detail",
        "last_assistant_question": (
            "Could you add one concrete detail about SQL — a tool, a task, or an outcome?"
        ),
        "answers_received": ["hmm"],
        "clarify_count": 1,
        "asked_questions": [],
    }
    d = decide_conversational_action("yeah", coach_context=ctx)
    assert d["action"] != "clarify"


# --- Scenario G: candidate asks for explanation ---

def test_scenario_g_strict_strips_spoilers_guided_allows_assistance_ladder():
    strict = system_prompt_for_mode("strict").lower()
    guided = system_prompt_for_mode("guided").lower()
    assert "hint" in strict and "never" in strict
    assert "assistance" in guided or "hint" in guided

    spoiled = "Great job! The answer is an API gateway. What is load balancing?"
    cleaned = strip_strict_spoilers(strip_strict_praise(spoiled))
    assert "the answer is" not in cleaned.lower()
    assert "great job" not in cleaned.lower()

    assert next_assistance_level(0, max_level=3) == 1
    assert next_assistance_level(3, max_level=3) is None


# --- Scenario H: behavioral ---

def test_scenario_h_behavioral_preferred_format_honored():
    fixed = apply_local_policy(
        _td(
            decision="next_area",
            question_type="conceptual",
            evaluation={"coverage": "good", "strengths": ["ok"], "gaps": []},
            next_question="Describe a conflict you resolved.",
            question_area="Leadership",
        ),
        {
            "mode": "strict",
            "turns_in_current_area": 1,
            "current_area": "Python",
            "remaining_areas": ["Leadership"],
            "preferred_format": "behavioral",
            "allowed_types": ["conceptual", "behavioral", "scenario"],
            "last_answer": "I mediated a sprint conflict by aligning on goals.",
            "questions_remaining": 5,
        },
    )
    assert fixed.question_type == "behavioral"


# --- Scenario I: project defense ---

def test_scenario_i_defense_uses_selected_projects_only():
    rules = defense_system_rules().lower()
    assert "never invent" in rules or "ask the candidate" in rules

    merged = merge_defense_question_areas(
        [{"topic": "DSA", "objective": "basics"}],
        [
            {
                "topic": "Music Database Management",
                "objective": "Project defense",
            }
        ],
    )
    topics = " ".join((a.get("topic") or "") for a in merged)
    assert "Music Database Management" in topics
    q = topic_focus_reply(
        {
            "title": "Music Database Management",
            "kind": "project",
            "details": {"purpose": "store songs", "technologies": "MySQL"},
        },
        coach_context={"current_topic": "", "answers_received": []},
    )
    assert "Music Database Management" in q
    assert "QCGNN" not in q


# --- Scenario J: completion ---

def test_scenario_j_completion_and_report_enrichment():
    fixed = apply_local_policy(
        _td(decision="follow_up", next_question="More?"),
        {
            "turns_in_current_area": 1,
            "current_area": "SQL",
            "remaining_areas": [],
            "questions_remaining": 0,
            "last_answer": "done",
        },
    )
    assert fixed.decision == "complete"

    class _T:
        def __init__(self, idx, q, a, cov):
            self.turn_index = idx
            self.question = q
            self.answer = a
            self.evaluation_coverage = cov
            self.evaluation_strengths = ["s"]
            self.evaluation_gaps = []
            self.evaluation_detail = {}
            self.question_type = "conceptual"
            self.question_area = "SQL"
            self.assisted = False

    turns = [_T(1, "What is a FK?", "Links tables", "good")]
    # RC-F1 fix: saved turn coverage wins over LLM row coverage.
    enriched = enrich_assessments_with_turns(
        {
            "question_assessments": [
                {"turn_index": 1, "coverage": "excellent", "observation": "llm rewrite"}
            ]
        },
        turns,
    )
    cov = enriched["question_assessments"][0].get("coverage")
    assert cov == "good"
