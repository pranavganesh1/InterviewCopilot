"""Duplicate / near-duplicate interview question detection."""

import pytest

from app.agents.interviewer import (
    TurnDecision,
    decision_violation,
    force_unique_decision,
    run_interviewer_turn,
)
from app.agents.question_dedupe import (
    concept_tags,
    is_duplicate_question,
    is_near_duplicate,
    question_similarity,
)


def test_exact_and_near_duplicates_detected():
    asked = ["Explain how hash collisions are resolved in a hashmap."]
    assert is_duplicate_question("Explain how hash collisions are resolved in a hashmap.", asked)
    assert is_duplicate_question("How are hash collisions resolved in a hashmap?", asked)
    assert not is_duplicate_question(
        "What is the time complexity of binary search on a sorted array?", asked
    )
    assert (
        question_similarity(
            "Explain two-pointer technique on arrays.",
            "Describe the two pointer technique for arrays.",
        )
        >= 0.72
    )


def test_semantic_array_definition_paraphrase_rejected():
    """Real Strict-Array failure: same learning objectives, different wording."""
    q1 = (
        "Can you explain what an array is, how its elements are stored "
        "contiguously in memory, and the differences between static "
        "(fixed-size) and dynamic (resizable) arrays?"
    )
    q2 = (
        "Please describe the definition of an array, how its elements are "
        "stored contiguously in memory, and contrast fixed-size (static) "
        "arrays with resizable (dynamic) arrays in terms of allocation "
        "and resizing behavior."
    )
    assert is_near_duplicate(q1, q2)
    assert is_duplicate_question(q2, [q1])
    tags1, tags2 = concept_tags(q1), concept_tags(q2)
    assert "contiguous_storage" in tags1 & tags2
    assert "static_vs_dynamic" in tags1 or "static_array" in tags1
    # Distinct concept must still be allowed.
    assert not is_duplicate_question(
        "Why is index-based random access O(1) in an array?",
        [q1],
    )


def test_decision_violation_flags_paraphrase():
    d = TurnDecision.model_validate(
        {
            "evaluation": {"coverage": "partial", "strengths": [], "gaps": []},
            "decision": "next_area",
            "next_question": "How do you resolve collisions in a hash map?",
            "question_area": "Hashmaps",
        }
    )
    v = decision_violation(
        d,
        {
            "turns_in_current_area": 0,
            "asked_questions": ["Explain how to resolve hash map collisions."],
            "questions_remaining": 10,
        },
    )
    assert v is not None
    assert "paraphrase" in v or "repeats" in v


def test_decision_violation_flags_concept_duplicate():
    d = TurnDecision.model_validate(
        {
            "evaluation": {"coverage": "good", "strengths": [], "gaps": []},
            "decision": "next_area",
            "next_question": (
                "Please describe the definition of an array, how its elements "
                "are stored contiguously in memory, and contrast fixed-size "
                "(static) arrays with resizable (dynamic) arrays."
            ),
            "question_area": "Arrays",
        }
    )
    v = decision_violation(
        d,
        {
            "turns_in_current_area": 0,
            "asked_questions": [
                "Can you explain what an array is, how its elements are stored "
                "contiguously in memory, and the differences between static "
                "(fixed-size) and dynamic (resizable) arrays?"
            ],
            "questions_remaining": 14,
        },
    )
    assert v is not None


def test_force_unique_produces_non_duplicate():
    d = TurnDecision.model_validate(
        {
            "evaluation": {"coverage": "good", "strengths": ["ok"], "gaps": []},
            "decision": "next_area",
            "next_question": "Explain arrays.",
            "question_area": "Arrays",
        }
    )
    payload = {
        "asked_questions": [
            "Explain the core idea behind Arrays with a concrete example.",
            "How would you implement Arrays efficiently, "
            "and what are the time and space trade-offs?",
        ],
        "remaining_areas": ["Sliding Window", "Prefix Sums"],
        "covered_areas": ["Arrays"],
        "questions_remaining": 12,
    }
    forced = force_unique_decision(d, payload)
    assert forced.decision != "complete"
    assert not is_duplicate_question(forced.next_question, payload["asked_questions"])


def test_fifteen_forced_questions_are_unique():
    """Simulate exhausted LLM: force_unique across 15 turns stays unique."""
    asked: list[str] = []
    areas = [
        "Array Fundamentals",
        "Dynamic Arrays",
        "Two Pointers",
        "Sliding Window",
        "Prefix Sums",
        "Binary Search",
        "Sorting",
        "Duplicates",
        "Subarrays",
        "Max Subarray",
        "Rotation",
        "Merge Sorted",
        "Hash Maps",
        "2D Arrays",
        "Complexity",
    ]
    for i in range(15):
        remaining = areas[i:]
        covered = areas[:i]
        d = TurnDecision.model_validate(
            {
                "evaluation": {"coverage": "none", "strengths": [], "gaps": []},
                "decision": "next_area",
                "next_question": asked[-1] if asked else "seed",
                "question_area": areas[min(i, len(areas) - 1)],
            }
        )
        payload = {
            "asked_questions": list(asked),
            "remaining_areas": remaining[1:] if remaining else [],
            "covered_areas": covered,
            "questions_remaining": 15 - i,
        }
        forced = force_unique_decision(d, payload)
        assert forced.decision != "complete", f"exhausted early at turn {i + 1}"
        assert not is_duplicate_question(forced.next_question, asked), forced.next_question
        asked.append(forced.next_question)

    assert len(asked) == 15
    assert len({q.lower() for q in asked}) == 15
    # Pairwise: no semantic collisions within the forced bank either.
    for i, qi in enumerate(asked):
        for qj in asked[i + 1 :]:
            assert not is_near_duplicate(qi, qj), (qi, qj)


def test_fifteen_array_questions_have_distinct_concepts():
    """force_unique for an Arrays-only track covers different learning objectives."""
    asked: list[str] = []
    # Seed with the exact duplicate pair that previously leaked.
    seed = (
        "Can you explain what an array is, how its elements are stored "
        "contiguously in memory, and the differences between static "
        "(fixed-size) and dynamic (resizable) arrays?"
    )
    asked.append(seed)
    for i in range(14):
        d = TurnDecision.model_validate(
            {
                "evaluation": {"coverage": "partial", "strengths": [], "gaps": []},
                "decision": "next_area",
                "next_question": (
                    "Please describe the definition of an array, how its elements "
                    "are stored contiguously in memory, and contrast fixed-size "
                    "(static) arrays with resizable (dynamic) arrays in terms of "
                    "allocation and resizing behavior."
                ),
                "question_area": "Arrays",
            }
        )
        payload = {
            "asked_questions": list(asked),
            "remaining_areas": [],
            "covered_areas": ["Arrays"],
            "questions_remaining": 15 - len(asked),
        }
        assert decision_violation(d, payload) is not None
        forced = force_unique_decision(d, payload)
        assert forced.decision != "complete", f"exhausted at {i + 2}"
        assert not is_duplicate_question(forced.next_question, asked)
        asked.append(forced.next_question)

    assert len(asked) == 15
    # Every pair must be concept-distinct under the detector.
    for i, qi in enumerate(asked):
        for qj in asked[i + 1 :]:
            assert not is_near_duplicate(qi, qj), (i + 1, i + 2, qi, qj)


@pytest.mark.asyncio
async def test_run_interviewer_turn_falls_back_instead_of_raising(monkeypatch):
    from app.agents import interviewer as mod

    async def always_dup(client, *, system, user_payload, schema, **_k):
        return TurnDecision.model_validate(
            {
                "evaluation": {"coverage": "none", "strengths": [], "gaps": []},
                "decision": "next_area",
                "next_question": "Same question about arrays",
                "question_area": "Arrays",
            }
        )

    monkeypatch.setattr(mod, "structured_completion", always_dup)
    decision = await run_interviewer_turn(
        payload={
            "mode": "strict",
            "asked_questions": ["Same question about arrays"],
            "turns_in_current_area": 0,
            "remaining_areas": ["Sliding Window"],
            "covered_areas": ["Arrays"],
            "questions_remaining": 10,
        }
    )
    assert decision.decision != "complete"
    assert decision.next_question != "Same question about arrays"
    assert not is_duplicate_question(decision.next_question, ["Same question about arrays"])


@pytest.mark.asyncio
async def test_run_interviewer_rejects_semantic_paraphrase(monkeypatch):
    from app.agents import interviewer as mod

    prior = (
        "Can you explain what an array is, how its elements are stored "
        "contiguously in memory, and the differences between static "
        "(fixed-size) and dynamic (resizable) arrays?"
    )
    paraphrase = (
        "Please describe the definition of an array, how its elements are "
        "stored contiguously in memory, and contrast fixed-size (static) "
        "arrays with resizable (dynamic) arrays in terms of allocation "
        "and resizing behavior."
    )

    async def always_paraphrase(client, *, system, user_payload, schema, **_k):
        return TurnDecision.model_validate(
            {
                "evaluation": {"coverage": "partial", "strengths": [], "gaps": []},
                "decision": "next_area",
                "next_question": paraphrase,
                "question_area": "Arrays",
            }
        )

    monkeypatch.setattr(mod, "structured_completion", always_paraphrase)
    decision = await run_interviewer_turn(
        payload={
            "mode": "strict",
            "asked_questions": [prior],
            "turns_in_current_area": 1,
            "remaining_areas": ["Two Pointers", "Sliding Window"],
            "covered_areas": ["Arrays"],
            "questions_remaining": 14,
        }
    )
    assert decision.decision != "complete"
    assert not is_near_duplicate(decision.next_question, prior)
    assert decision.next_question != paraphrase
