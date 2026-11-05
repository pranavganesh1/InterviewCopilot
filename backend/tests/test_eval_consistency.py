"""Evaluator guards, consistency repair, and coverage-based scoring."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.agents.interviewer import (
    COVERAGE_RUBRIC,
    EVALUATE_SYSTEM_PROMPT,
    AnswerEvaluation,
    evaluate_answer_with_meta,
    evaluation_inconsistencies,
)
from app.services.feedback_service import COVERAGE_POINTS, overall_score_from_content

FIXTURES = Path(__file__).parent / "fixtures" / "eval_samples.json"


def _samples() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_rubric_constant_in_evaluator_prompt():
    assert "none      = no relevant content, or the answer is wrong" in COVERAGE_RUBRIC
    assert COVERAGE_RUBRIC.strip() in EVALUATE_SYSTEM_PROMPT
    assert "never invent mistakes" in EVALUATE_SYSTEM_PROMPT.lower()
    assert EVALUATE_SYSTEM_PROMPT.count("Coverage rubric:") == 1


@pytest.mark.asyncio
async def test_guards_skip_llm_for_empty_idk_short(monkeypatch):
    calls = 0

    async def boom(*_a, **_k):
        nonlocal calls
        calls += 1
        raise AssertionError("LLM must not be called for guarded answers")

    monkeypatch.setattr("app.agents.interviewer.structured_completion", boom)

    for answer, check in (
        ("", "empty_answer"),
        ("I don't know", "idk_answer"),
        ("idk", "idk_answer"),
        ("ok", "too_short_answer"),
    ):
        ev, checks = await evaluate_answer_with_meta(
            {"last_answer": answer, "last_question": "What is an array?", "mode": "strict"}
        )
        assert ev.coverage == "none"
        assert check in checks
        assert ev.gaps
    assert calls == 0


@pytest.mark.asyncio
async def test_inconsistent_llm_triggers_repair_then_fallback(monkeypatch):
    calls: list[dict] = []

    async def fake_structured(client, *, system, user_payload, schema, **kwargs):
        assert kwargs.get("temperature") == 0
        calls.append(user_payload)
        # Always return inconsistent: excellent with no strengths.
        return AnswerEvaluation(
            coverage="excellent",
            strengths=[],
            gaps=[],
            expected_answer_explanation="x",
        )

    monkeypatch.setattr("app.agents.interviewer.structured_completion", fake_structured)
    ev, checks = await evaluate_answer_with_meta(
        {
            "last_answer": "A thorough explanation of two-sum with a hash map and O(n) time.",
            "last_question": "Explain two-sum.",
            "mode": "strict",
        }
    )
    assert len(calls) == 2  # initial + one repair
    assert "high_label_without_strengths" in checks
    assert "fallback_after_repair" in checks
    assert ev.coverage == "partial"
    assert ev.gaps


@pytest.mark.asyncio
async def test_consistent_llm_output_passes(monkeypatch):
    calls = 0

    async def fake_structured(client, *, system, user_payload, schema, **kwargs):
        nonlocal calls
        calls += 1
        assert kwargs.get("temperature") == 0
        return AnswerEvaluation(
            coverage="good",
            strengths=["Clear hash-map approach"],
            gaps=["Did not discuss space complexity"],
            expected_answer_explanation="One-pass map of complements.",
            time_complexity="O(n)",
            space_complexity="O(n)",
        )

    monkeypatch.setattr("app.agents.interviewer.structured_completion", fake_structured)
    ev, checks = await evaluate_answer_with_meta(
        {
            "last_answer": (
                "Use a hashmap; for each value look up target-value. O(n) time O(n) space."
            ),
            "last_question": "Explain two-sum with complexities.",
            "mode": "strict",
            "open_question_type": "coding",
        }
    )
    assert calls == 1
    assert checks == []
    assert ev.coverage == "good"
    assert evaluation_inconsistencies(ev, is_code=True) == []


def test_overall_score_uses_answered_questions_only():
    content = {
        "question_assessments": [
            {"coverage": "excellent"},  # 100
            {"coverage": "partial"},  # 50
        ]
    }
    assert overall_score_from_content(content) == 75
    assert overall_score_from_content({"question_assessments": []}) is None
    assert overall_score_from_content(None) is None
    # Labels map only through COVERAGE_POINTS — no free-form LLM numbers.
    assert set(COVERAGE_POINTS) == {"none", "partial", "good", "excellent"}


def test_eval_samples_fixture_shape():
    samples = _samples()
    assert len(samples) >= 15
    topics = {s["topic"] for s in samples}
    assert {"arrays", "hash_maps", "operating_systems"} <= topics
    for s in samples:
        assert s["expected"] in COVERAGE_POINTS
        assert s["question"] and "answer" in s and s["reason"]


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_eval_stability_against_samples():
    """Hit the real gateway. Skipped unless RUN_LIVE_EVAL=1."""
    if os.environ.get("RUN_LIVE_EVAL") != "1":
        pytest.skip("Set RUN_LIVE_EVAL=1 to run live evaluation stability checks")

    levels = ["none", "partial", "good", "excellent"]
    rank = {lab: i for i, lab in enumerate(levels)}
    samples = [s for s in _samples() if str(s["answer"]).strip()]

    exact = 0
    within_one = 0
    stable = 0
    total = 0
    for sample in samples:
        runs: list[str] = []
        for _ in range(3):
            ev, _ = await evaluate_answer_with_meta(
                {
                    "mode": "strict",
                    "brief": {"summary": sample["topic"]},
                    "last_question": sample["question"],
                    "last_answer": sample["answer"],
                }
            )
            runs.append(ev.coverage)
        total += 1
        expected = sample["expected"]
        # Majority label for agreement metrics.
        majority = max(set(runs), key=runs.count)
        if majority == expected:
            exact += 1
        if abs(rank[majority] - rank[expected]) <= 1:
            within_one += 1
        if len(set(runs)) == 1:
            stable += 1

    exact_rate = exact / total
    within_rate = within_one / total
    stable_rate = stable / total
    print(
        f"live_eval exact={exact_rate:.2%} within_one={within_rate:.2%} "
        f"stable={stable_rate:.2%} n={total}"
    )
    assert stable_rate >= 0.80, f"run-to-run stability {stable_rate:.2%} < 80%"
    assert within_rate >= 0.90, f"within-one-level {within_rate:.2%} < 90%"
