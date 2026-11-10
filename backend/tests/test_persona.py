"""Interviewer personality selection (no migration, stubbed LLM)."""

import uuid

import httpx
import pytest

from app.agents.interviewer import system_prompt_for_mode
from app.agents.persona import (
    DEFAULT_PERSONA_ID,
    PERSONAS,
    bias_plan_for_persona,
    get_persona,
    normalize_persona_id,
    persona_prompt_block,
)
from app.agents.question_quality import strict_praise_violation
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.interview import InterviewSession
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.services import feedback_service
from app.services import probe as probe_service


def test_persona_prompt_blocks_differ_and_balanced_is_empty():
    assert persona_prompt_block("balanced") == ""
    blocks = {
        pid: persona_prompt_block(pid, mode="strict")
        for pid in PERSONAS
        if pid != "balanced"
    }
    assert len(set(blocks.values())) == len(blocks)
    for block in blocks.values():
        assert "Active interviewer persona" in block
        assert "never praise" in block.lower() or "never evaluate" in block.lower()


def test_system_prompt_balanced_equals_legacy():
    assert system_prompt_for_mode("strict") == system_prompt_for_mode("strict", "balanced")
    assert system_prompt_for_mode("guided") == system_prompt_for_mode("guided", "balanced")
    architect = system_prompt_for_mode("strict", "architect")
    assert "Strict Architect" in architect
    assert architect != system_prompt_for_mode("strict", "balanced")


def test_normalize_rejects_unknown():
    assert normalize_persona_id(None) == DEFAULT_PERSONA_ID
    assert normalize_persona_id("") == DEFAULT_PERSONA_ID
    with pytest.raises(ValueError, match="invalid_persona"):
        normalize_persona_id("cartoon_villain")


def test_plan_bias_keeps_length_and_all_slots():
    plan = [
        {"topic": "Definitions", "objective": "define X", "format": "conceptual"},
        {"topic": "Systems design", "objective": "trade-offs", "format": "case_study"},
        {"topic": "Team delivery", "objective": "ownership", "format": "behavioral"},
        {"topic": "Complexity", "objective": "why it works", "format": "numeric"},
        {"topic": "Other", "objective": "misc", "format": "mcq"},
        {"topic": "Extra", "objective": "more", "format": "coding"},
    ]
    for pid in PERSONAS:
        out = bias_plan_for_persona(plan, pid)
        assert len(out) == len(plan)
        topics = {s["topic"] for s in out}
        assert topics == {s["topic"] for s in plan}


def test_probe_templates_differ_by_persona():
    answer = "I used a hash map for O(1) lookups on the ids."
    balanced = probe_service.craft_answer_probe(
        answer=answer, area="Hashmaps", asked=[], mode="strict", seed=0, persona_id="balanced"
    )
    architect = probe_service.craft_answer_probe(
        answer=answer, area="Hashmaps", asked=[], mode="strict", seed=0, persona_id="architect"
    )
    academic = probe_service.craft_answer_probe(
        answer=answer, area="Hashmaps", asked=[], mode="strict", seed=0, persona_id="academic"
    )
    assert balanced and architect and academic
    assert architect["next_question"] != balanced["next_question"]
    assert academic["next_question"] != architect["next_question"]
    for probe in (balanced, architect, academic):
        assert strict_praise_violation(probe["next_question"]) is None


def test_domain_neutral_wording_for_non_programming():
    for pid in PERSONAS:
        block = persona_prompt_block(pid, mode="strict")
        if not block:
            continue
        assert "Domain-neutral" in block or "domain-neutral" in block.lower()
        assert "programming" not in block.lower()
        assert "software engineer" not in block.lower()


@pytest.mark.asyncio
async def test_invalid_persona_returns_422(clean_users_table, monkeypatch):
    from app.agents.interviewer import TurnDecision

    async def fake_turn(*_a, **_k):
        return TurnDecision(
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            decision="next_area",
            next_question="What is a cell?",
            question_area="Biology",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"p-{uuid.uuid4()}@ex.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Cell biology")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Cells",
                    "competencies": [
                        {"name": "Membranes", "description": "m", "importance": "core"}
                    ],
                    "question_areas": [{"topic": "Membranes", "guidance": "structure"}],
                },
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        track_id = track.id

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "persona_id": "not_a_real_persona"},
            cookies={"ic_access": token},
        )
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_persona_stored_returned_immutable_and_in_report(
    clean_users_table, monkeypatch
):
    from app.agents.interviewer import TurnDecision

    calls = {"n": 0}

    async def fake_turn(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return TurnDecision(
                evaluation={"coverage": "none", "strengths": [], "gaps": []},
                decision="next_area",
                next_question="What is a primary source?",
                question_area="Sources",
            )
        return TurnDecision(
            evaluation={"coverage": "good", "strengths": ["clear"], "gaps": []},
            decision="complete",
            next_question="",
            question_area="Sources",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)

    async def _fail(**_k):
        raise RuntimeError("stub")

    monkeypatch.setattr(feedback_service, "run_feedback_agent", _fail)
    published: list[str] = []

    async def fake_publish(session_id, *_a, **_k):
        published.append(str(session_id))

    monkeypatch.setattr(
        "app.services.interview_service.publish_feedback_job", fake_publish
    )

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"p2-{uuid.uuid4()}@ex.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="History methods")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Historiography",
                    "competencies": [{"name": "Sources", "description": "s", "importance": "core"}],
                    "question_areas": [{"topic": "Sources", "guidance": "primary"}],
                },
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        track_id = track.id

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "persona_id": "hiring_manager", "duration_minutes": 30},
            cookies={"ic_access": token},
        )
        assert started.status_code == 201
        body = started.json()
        assert body["session"]["persona_id"] == "hiring_manager"
        assert body["session"]["persona_name"] == get_persona("hiring_manager").name
        sid = body["session"]["id"]

        fetched = await client.get(f"/api/v1/sessions/{sid}", cookies={"ic_access": token})
        assert fetched.json()["session"]["persona_id"] == "hiring_manager"

        done = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "A contemporary document from the period"},
            cookies={"ic_access": token},
        )
        assert done.status_code == 200
        assert done.json()["completed"] is True

    async with SessionFactory() as session:
        row = await session.get(InterviewSession, uuid.UUID(sid))
        opts = probe_service.session_opts_from_plan(row.question_plan)
        assert opts["persona_id"] == "hiring_manager"

    async with SessionFactory() as session:
        result = await feedback_service.process_session_feedback(session, sid)
    assert result["report"]["content"]["persona_id"] == "hiring_manager"
    assert "persona_name" in result["report"]["content"]


@pytest.mark.asyncio
async def test_scoring_identical_across_personas(clean_users_table, monkeypatch):
    from app.agents.interviewer import TurnDecision

    scores = []
    for persona in ("balanced", "architect", "academic"):
        calls = {"n": 0}

        async def fake_turn(*_a, _calls=calls, **_k):
            _calls["n"] += 1
            if _calls["n"] == 1:
                return TurnDecision(
                    evaluation={"coverage": "none", "strengths": [], "gaps": []},
                    decision="next_area",
                    next_question="State Ohm's law.",
                    question_area="Ohm",
                )
            return TurnDecision(
                evaluation={"coverage": "partial", "strengths": ["ok"], "gaps": ["depth"]},
                decision="complete",
                next_question="",
                question_area="Ohm",
            )

        monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)

        async with SessionFactory() as session:
            user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"{persona}-{uuid.uuid4()}@ex.com")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            track = Track(user_id=user.id, track_type="topic", subject="Electronics")
            session.add(track)
            await session.commit()
            await session.refresh(track)
            session.add(
                InterviewBrief(
                    track_id=track.id,
                    version=1,
                    content={
                        "summary": "Circuits",
                        "competencies": [
                            {"name": "Ohm", "description": "v", "importance": "core"}
                        ],
                        "question_areas": [{"topic": "Ohm", "guidance": "V=IR"}],
                    },
                )
            )
            await session.commit()
            token = create_access_token(str(user.id))
            track_id = track.id

        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = await client.post(
                f"/api/v1/tracks/{track_id}/sessions",
                json={"mode": "strict", "persona_id": persona},
                cookies={"ic_access": token},
            )
            assert started.status_code == 201
            sid = started.json()["session"]["id"]
            answered = await client.post(
                f"/api/v1/sessions/{sid}/turns",
                json={"answer": "V equals I times R"},
                cookies={"ic_access": token},
            )
            assert answered.status_code == 200
            scores.append(answered.json()["evaluation"]["coverage"])

    assert len(set(scores)) == 1
    assert scores[0] == "partial"


def test_old_report_without_persona_fields_is_fine():
    content = {"summary_overview": "ok", "question_assessments": []}
    assert content.get("persona_id") is None
    assert content.get("persona_name") is None
