import pytest

from app.agents.track_creator import (
    BankQuestion,
    InterviewBriefContent,
)
from app.services.track_service import build_track_creator_brief


def _brief_with_bank(questions: list[str]):
    return InterviewBriefContent(
        summary="DSA interview",
        question_areas=[{"topic": "Hashmaps", "guidance": "collisions"}],
        question_bank=[
            BankQuestion(
                area="Hashmaps",
                question=q,
                difficulty="intermediate",
                type="conceptual",
                expected_answer_sketch="buckets, hashing",
            )
            for q in questions
        ],
    )


@pytest.mark.asyncio
async def test_bank_attached_to_brief(monkeypatch):
    async def fake_turn(*args, **kwargs):
        return _brief_with_bank(
            [
                "Explain how a hashmap handles collisions.",
                "What is the average lookup complexity of a hashmap?",
                "Compare hashmap vs array lookup trade-offs.",
            ]
        )

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)

    result = await build_track_creator_brief(
        objective={"track_type": "topic", "subject": "DSA"}, vault_summary=[]
    )
    bank = result["question_bank"]
    assert len(bank) == 3
    assert bank[0]["area"] == "Hashmaps"


@pytest.mark.asyncio
async def test_dedupe_drops_near_duplicates(monkeypatch):
    async def fake_turn(*args, **kwargs):
        return _brief_with_bank(
            [
                "Explain how a hashmap handles collisions.",
                "Explain how a hashmap handles collisions in practice.",  # near-dupe
                "Compare hashmap vs array lookup trade-offs.",
            ]
        )

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)

    result = await build_track_creator_brief(
        objective={"track_type": "topic", "subject": "DSA"}, vault_summary=[]
    )
    questions = [q["question"] for q in result["question_bank"]]
    assert len(questions) == 2
    assert "Compare hashmap vs array lookup trade-offs." in questions


@pytest.mark.asyncio
async def test_empty_bank_never_blocks(monkeypatch):
    async def fake_turn(*args, **kwargs):
        return _brief_with_bank([])

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)

    result = await build_track_creator_brief(
        objective={"track_type": "topic", "subject": "DSA"}, vault_summary=[]
    )
    assert result["question_bank"] == []
