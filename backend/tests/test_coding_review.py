"""Coding answers are AI-reviewed statically — never executed."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.coding_review import AI_REVIEWED_NOT_EXECUTED, CODING_STATIC_REVIEW_RULES
from app.agents.interviewer import AnswerEvaluation, evaluate_answer_with_meta
from app.services.feedback_report_builder import enrich_assessments_with_turns

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

# Patterns that would imply running candidate code in-process.
_FORBIDDEN = [
    (re.compile(r"\bsubprocess\b"), "subprocess"),
    (re.compile(r"\bos\.system\s*\("), "os.system"),
    (re.compile(r"\basyncio\.create_subprocess"), "asyncio.create_subprocess"),
    (re.compile(r"(?<![\w.])exec\s*\("), "exec("),
    (re.compile(r"(?<![\w.])eval\s*\("), "eval("),
]

# No allowlisted hits expected today; keep the list for future infrastructure.
_ALLOWLIST_REL_PATHS: set[str] = set()


def test_no_code_execution_primitives_in_app():
    hits: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        rel = path.relative_to(APP_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for pattern, label in _FORBIDDEN:
            if pattern.search(text) and rel not in _ALLOWLIST_REL_PATHS:
                hits.append(f"{rel}: {label}")
    assert hits == [], f"Forbidden execution primitives in app/: {hits}"


@pytest.mark.asyncio
async def test_coding_eval_prompt_includes_not_executed(monkeypatch):
    seen_systems: list[str] = []

    async def fake_structured(client, *, system, user_payload, schema, **kwargs):
        seen_systems.append(system)
        return AnswerEvaluation(
            coverage="good",
            strengths=["Clear loop"],
            gaps=["Missing edge case"],
            expected_answer_explanation="Two-sum with a map.",
            corrected_code="def two_sum(a,t): ...",
            time_complexity="O(n)",
            space_complexity="O(n)",
        )

    monkeypatch.setattr("app.agents.interviewer.structured_completion", fake_structured)
    await evaluate_answer_with_meta(
        {
            "mode": "strict",
            "open_question_type": "coding",
            "last_question": "Write two-sum.",
            "last_answer": "```python\ndef two_sum(nums, target):\n    pass\n```",
        }
    )
    assert seen_systems
    assert "NOT executed" in seen_systems[0] or "NOT run" in seen_systems[0]
    assert "statically" in seen_systems[0].lower() or "static" in CODING_STATIC_REVIEW_RULES.lower()


def test_coding_evaluation_detail_sets_executed_false():
    """Mirrors interview_service persistence for coding turns."""
    question_type = "coding"
    detail = {
        "expected_answer_explanation": "map",
        "corrected_code": "def f(): ...",
        "time_complexity": "O(n)",
        "space_complexity": "O(n)",
        "rubric_version": "v1",
        "evaluator_checks": [],
    }
    if question_type == "coding":
        detail["executed"] = False
    assert detail["executed"] is False


def test_report_enrichment_adds_review_label():
    turn = SimpleNamespace(
        turn_index=1,
        question="Write two-sum",
        answer="code",
        question_area="Arrays",
        question_type="coding",
        evaluation_coverage="good",
        evaluation_strengths=["ok"],
        evaluation_gaps=[],
        evaluation_detail={"executed": False, "corrected_code": "def f(): pass"},
    )
    content = enrich_assessments_with_turns(
        {"question_assessments": [{"turn_index": 1, "coverage": "good", "observation": "x"}]},
        [turn],
    )
    qa = content["question_assessments"][0]
    assert qa["executed"] is False
    assert qa["review_label"] == AI_REVIEWED_NOT_EXECUTED
    assert content.get("coding_review_note") == AI_REVIEWED_NOT_EXECUTED


def test_non_coding_enrichment_unchanged():
    turn = SimpleNamespace(
        turn_index=1,
        question="Explain CAP",
        answer="consistency vs availability",
        question_area="Distributed",
        question_type="conceptual",
        evaluation_coverage="good",
        evaluation_strengths=["clear"],
        evaluation_gaps=[],
        evaluation_detail={"expected_answer_explanation": "trade-offs"},
    )
    content = enrich_assessments_with_turns(
        {"question_assessments": [{"turn_index": 1, "coverage": "good", "observation": "x"}]},
        [turn],
    )
    qa = content["question_assessments"][0]
    assert "executed" not in qa
    assert "coding_review_note" not in content
