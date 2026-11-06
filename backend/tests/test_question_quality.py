"""One-focus questions, neutral Strict wording, and additive answer formats."""

import uuid
from types import SimpleNamespace

import pytest

from app.agents.interviewer import (
    TurnDecision,
    apply_local_policy,
    decision_violation,
)
from app.agents.question_plan import deterministic_question_plan
from app.agents.question_quality import (
    format_for_slot,
    mcq_violation,
    prepare_bank_question,
    question_focus_violation,
    repair_single_focus,
    score_mcq,
)
from app.services.feedback_report_builder import enrich_assessments_with_turns
from app.services.interview_service import _turn_dict

OPTIONS = ["O(1) average", "O(n) average", "O(log n) average", "O(n log n) average"]
STACKED = (
    "How do you access, slice and handle out-of-bounds errors in Python versus Java?"
)


def _decision(**overrides) -> TurnDecision:
    body = {
        "evaluation": {"coverage": "partial", "strengths": [], "gaps": []},
        "decision": "next_area",
        "next_question": "What is a hash map?",
        "question_area": "Hashing",
        "question_type": "conceptual",
    }
    body.update(overrides)
    return TurnDecision.model_validate(body)


def test_stacked_question_is_rejected_and_repaired():
    assert question_focus_violation(STACKED)
    repaired = repair_single_focus(
        "How do you slice a list, and also how do you copy one? What about tuples?"
    )
    assert repaired.count("?") == 1
    assert question_focus_violation(repaired) is None
    decision = apply_local_policy(
        _decision(next_question="How do you slice a list, and also how do you copy one?"),
        {"mode": "strict"},
    )
    assert "and also" not in decision.next_question.lower()
    assert decision_violation(_decision(next_question=STACKED), {"mode": "strict"})


def test_strict_strips_praise_and_guided_keeps_it():
    praised = "Good start. What is a hash map?"
    strict = apply_local_policy(_decision(next_question=praised), {"mode": "strict"})
    guided = apply_local_policy(_decision(next_question=praised), {"mode": "guided"})
    assert strict.next_question == "What is a hash map?"
    assert guided.next_question == praised
    assert decision_violation(_decision(next_question=praised), {"mode": "strict"})
    assert decision_violation(_decision(next_question=praised), {"mode": "guided"}) is None


def test_mcq_scoring_is_deterministic_and_shape_is_checked():
    assert score_mcq("2", 2)[0] == "excellent"
    assert score_mcq("0", 2)[0] == "none"
    assert mcq_violation(OPTIONS, 2) is None
    assert mcq_violation(OPTIONS, None)
    assert mcq_violation(OPTIONS[:3], 0)
    assert mcq_violation(["same", "same", "other", "left"], 0)


def test_turn_hides_the_key_until_the_report():
    turn = SimpleNamespace(
        turn_index=1,
        question_area="Hashing",
        question="What is the average lookup cost?",
        question_type="mcq",
        answer=None,
        evaluation_coverage="excellent",
        evaluation_strengths=["Selected the correct option."],
        evaluation_gaps=[],
        evaluation_detail={
            "question_meta": {
                "options": OPTIONS,
                "correct_index": 0,
                "explanation": "Hashing is amortized constant time.",
                "objective": "Recall hashmap lookup cost.",
            }
        },
    )
    hidden = _turn_dict(turn)
    assert hidden["options"] == OPTIONS
    assert "correct_index" not in hidden
    assert "explanation" not in hidden
    revealed = _turn_dict(turn, reveal=True)
    assert revealed["correct_index"] == 0
    turn.answer = "0"
    report = enrich_assessments_with_turns({"question_assessments": []}, [turn])
    row = report["question_assessments"][0]
    assert row["chosen_option"] == OPTIONS[0]
    assert row["correct_option"] == OPTIONS[0]
    assert row["explanation"]


@pytest.mark.asyncio
async def test_code_read_is_stored_with_its_snippet(monkeypatch):
    from app.services import interview_service as svc

    async def no_turns(*_args, **_kwargs):
        return 0

    class Memory:
        async def commit(self):
            return None

        async def refresh(self, _turn):
            return None

        def add(self, _turn):
            return None

    monkeypatch.setattr(svc, "_count_turns", no_turns)
    snippet = "xs = [1, 2]\nprint(xs[:5])"
    decision = _decision(
        question_type="code_read",
        next_question="What does this slice print?",
        code_snippet=snippet,
        objective="Predict a slice that runs past the end.",
    )
    turn = await svc._append_turn(Memory(), SimpleNamespace(id=uuid.uuid4()), decision)
    assert turn.evaluation_detail["question_meta"]["code_snippet"] == snippet
    assert _turn_dict(turn)["code_snippet"] == snippet


def test_non_programming_plan_has_no_code_types():
    brief = {"summary": "Product sense", "question_areas": [{"topic": "Prioritization"}]}
    formats = [slot["format"] for slot in deterministic_question_plan(brief, 15)]
    assert "coding" not in formats
    assert "code_read" not in formats
    assert "mcq" in formats
    programming = [format_for_slot(i, programming=True) for i in range(15)]
    assert programming.count("conceptual") == 8
    assert programming.count("mcq") == 3
    assert programming.count("code_read") == 2
    assert programming.count("coding") == 2


def test_dedupe_applies_across_types_and_bad_bank_rows_drop():
    asked = "What is a hash map?"
    violation = decision_violation(
        _decision(question_type="mcq", next_question=asked, options=OPTIONS, correct_index=0),
        {"mode": "guided", "asked_questions": [asked], "programming_track": True},
    )
    assert violation and "repeats" in violation
    dropped = prepare_bank_question(
        {"area": "Lists", "question": STACKED, "type": "conceptual"},
        programming=True,
    )
    assert dropped is None
    coerced = prepare_bank_question(
        {
            "area": "Stories",
            "question": "What trade-off did you choose?",
            "type": "coding",
            "code_snippet": "print(1)",
        },
        programming=False,
    )
    assert coerced is not None
    assert coerced["type"] == "conceptual"
    assert coerced["code_snippet"] == ""
