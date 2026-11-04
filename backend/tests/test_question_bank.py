import pytest

from app.agents.track_creator import (
    BankQuestion,
    InterviewBriefContent,
)
from app.services.track_service import build_track_creator_brief


def _brief_content():
    return InterviewBriefContent(
        summary="DSA interview",
        question_areas=[
            {"topic": "Hashmaps", "guidance": "collisions"},
            {"topic": "Big-O", "guidance": "complexity"},
        ],
    )


def _bank(questions: list[str]):
    return [
        BankQuestion(
            area="Hashmaps",
            question=q,
            difficulty="intermediate",
            type="conceptual",
            expected_answer_sketch="buckets, hashing, collisions",
        )
        for q in questions
    ]


@pytest.mark.asyncio
async def test_bank_attached_to_brief(monkeypatch):
    async def fake_turn(*args, **kwargs):
        return _brief_content()

    async def fake_bank(*args, **kwargs):
        return _bank(
            [
                "Explain how a hashmap handles collisions.",
                "What is the average lookup complexity of a hashmap?",
                "Compare hashmap vs array lookup trade-offs.",
            ]
        )

    async def fake_judge(*args, **kwargs):
        from app.agents.track_creator import BankJudgeVerdict

        return BankJudgeVerdict(
            verdicts=[
                {"index": 0, "accept": True, "reason": "clear"},
                {"index": 1, "accept": True, "reason": "clear"},
                {"index": 2, "accept": True, "reason": "clear"},
            ]
        )

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)
    monkeypatch.setattr(svc, "run_bank_builder_turn", fake_bank)
    monkeypatch.setattr(svc, "run_bank_judge_turn", fake_judge)

    result = await build_track_creator_brief(
        objective={"track_type": "topic", "subject": "DSA"}, vault_summary=[]
    )
    bank = result["question_bank"]
    assert len(bank) == 3
    assert bank[0]["area"] == "Hashmaps"


@pytest.mark.asyncio
async def test_rejected_questions_regenerated_once(monkeypatch):
    async def fake_turn(*args, **kwargs):
        return _brief_content()

    async def fake_bank(*args, **kwargs):
        return _bank(["Bad vague question one?", "Good hashmap question?", "Another good one?"])

    judge_calls = {"n": 0}

    async def fake_judge(*args, **kwargs):
        from app.agents.track_creator import BankJudgeVerdict

        judge_calls["n"] += 1
        if judge_calls["n"] == 1:
            return BankJudgeVerdict(
                verdicts=[
                    {"index": 0, "accept": False, "reason": "too vague"},
                    {"index": 1, "accept": True, "reason": "clear"},
                    {"index": 2, "accept": True, "reason": "clear"},
                ]
            )
        return BankJudgeVerdict(verdicts=[{"index": 0, "accept": True, "reason": "fixed"}])

    regen_calls = {"n": 0}

    async def fake_regen(*args, **kwargs):
        regen_calls["n"] += 1
        return _bank(["Precise collision-resolution question?"])

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)
    monkeypatch.setattr(svc, "run_bank_builder_turn", fake_bank)
    monkeypatch.setattr(svc, "run_bank_judge_turn", fake_judge)
    monkeypatch.setattr(svc, "run_bank_regeneration_turn", fake_regen)

    bank = (
        await build_track_creator_brief(
            objective={"track_type": "topic", "subject": "DSA"}, vault_summary=[]
        )
    )["question_bank"]
    assert regen_calls["n"] == 1
    assert len(bank) == 3
    questions = [b["question"] for b in bank]
    assert "Precise collision-resolution question?" in questions
    assert "Bad vague question one?" not in questions


@pytest.mark.asyncio
async def test_generation_crash_ships_empty_bank(monkeypatch):
    async def fake_turn(*args, **kwargs):
        return _brief_content()

    async def fake_bank(*args, **kwargs):
        raise RuntimeError("llm down")

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)
    monkeypatch.setattr(svc, "run_bank_builder_turn", fake_bank)

    bank = (
        await build_track_creator_brief(
            objective={"track_type": "topic", "subject": "DSA"}, vault_summary=[]
        )
    )["question_bank"]
    assert bank == []
