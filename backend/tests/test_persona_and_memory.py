"""Persona, covered_so_far memory, and Strict spoiler stripping."""

from types import SimpleNamespace

from app.agents.interviewer import (
    PERSONA_BLOCK,
    TurnDecision,
    apply_local_policy,
    strip_strict_spoilers,
    system_prompt_for_mode,
)
from app.agents.question_dedupe import is_duplicate_question
from app.services.interview_service import build_covered_so_far


def test_strict_prompt_has_persona_and_no_hint_rule():
    strict = system_prompt_for_mode("strict")
    assert "Persona (human interviewer)" in strict
    assert PERSONA_BLOCK.strip()[:20] in strict
    assert "never put hints" in strict.lower() or "never hint" in strict.lower()


def test_strip_strict_spoilers_removes_correctness_reveal():
    raw = (
        "That's correct — great job! Let's switch gears to trees. "
        "How would you traverse a binary tree?"
    )
    cleaned = strip_strict_spoilers(raw)
    assert "correct" not in cleaned.lower()
    assert "binary tree" in cleaned.lower()

    decision = TurnDecision.model_validate(
        {
            "evaluation": {"coverage": "good", "strengths": [], "gaps": []},
            "decision": "next_area",
            "next_question": raw,
            "question_area": "Trees",
        }
    )
    fixed = apply_local_policy(decision, {"mode": "strict", "turns_in_current_area": 0})
    assert "correct" not in fixed.next_question.lower()
    assert "binary tree" in fixed.next_question.lower()


def test_covered_so_far_with_plan_and_null_plan():
    turns = [
        SimpleNamespace(
            question_area="Hashmaps",
            question="Explain collisions?",
            answer="chaining",
            evaluation_coverage="partial",
        ),
        SimpleNamespace(
            question_area="Trees",
            question="What is a BST?",
            answer="ordered tree",
            evaluation_coverage="none",
        ),
    ]
    plan = [
        {"topic": "Hashmaps", "objective": "collision resolution", "difficulty": "foundational"},
        {"topic": "Trees", "objective": "BST invariants", "difficulty": "intermediate"},
        {"topic": "Graphs", "objective": "BFS vs DFS", "difficulty": "advanced"},
    ]
    mem = build_covered_so_far(turns, plan=plan, questions_asked=2)
    assert "collision resolution" in mem["covered_objectives"]
    assert mem["next_planned_objective"]["topic"] == "Graphs"
    assert len(mem["weak_areas"]) == 2

    null_mem = build_covered_so_far(turns, plan=None, questions_asked=2)
    assert null_mem["next_planned_objective"] is None
    assert "Hashmaps" in null_mem["covered_objectives"]
    assert "Trees" in null_mem["covered_objectives"]


def test_weak_area_revisit_must_not_reuse_question():
    asked = ["Explain how hashmaps handle collisions."]
    revisit = "Explain how hashmaps handle collisions."
    different = "When would you pick open addressing over chaining, and why?"
    assert is_duplicate_question(revisit, asked)
    assert not is_duplicate_question(different, asked)
