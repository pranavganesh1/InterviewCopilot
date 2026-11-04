"""Task 8: Guided progressive assistance."""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.agents.assistance import (
    AssistanceContent,
    is_coding_question,
    next_assistance_level,
)
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.feedback import ProgressionState
from app.models.interview import SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User


def test_next_assistance_level_is_backend_owned():
    assert next_assistance_level(0) == 1
    assert next_assistance_level(1) == 2
    assert next_assistance_level(2) == 3
    assert next_assistance_level(3) is None
    assert next_assistance_level(3, max_level=5) == 4
    assert next_assistance_level(5, max_level=5) is None


def test_coding_question_detection():
    assert is_coding_question(
        "Write a function that returns two sum indices.", "Arrays"
    )
    assert not is_coding_question(
        "Tell me about a conflict on your team.", "Behavioral"
    )


async def _seed(monkeypatch, *, mode: str = "guided", guided_state: str = "UNLOCKED"):
    from app.agents.interviewer import TurnDecision

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"as-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Caching")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Caching",
                    "competencies": [
                        {"name": "Redis", "description": "cache", "importance": "core"}
                    ],
                    "question_areas": [{"topic": "Redis", "guidance": "TTLs"}],
                },
            )
        )
        session.add(
            ProgressionState(
                track_id=track.id, strict_completed=3, guided_state=guided_state
            )
        )
        await session.commit()

    async def fake_turn(*args, **kwargs):
        return TurnDecision(
            evaluation={"coverage": "partial", "strengths": [], "gaps": ["ttl"]},
            decision="follow_up",
            next_question="How would you choose a Redis TTL?",
            question_area="Redis",
        )

    levels_seen: list[int] = []

    async def fake_assist(*, payload: dict):
        level = payload["level"]
        levels_seen.append(level)
        return AssistanceContent(
            level=int(level),
            assistance_type=str(payload["assistance_type"]),
            content=f"help-level-{level}",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    monkeypatch.setattr("app.services.interview_service.run_assistance_turn", fake_assist)
    return (
        user,
        create_access_token(str(user.id)),
        track.id,
        mode,
        levels_seen,
    )


async def _start(client, token, track_id, mode):
    r = await client.post(
        f"/api/v1/tracks/{track_id}/sessions",
        json={"mode": mode},
        cookies={"ic_access": token},
    )
    assert r.status_code == 201, r.text
    return r.json()["session"]["id"]


@pytest.mark.asyncio
async def test_guided_assistance_progresses_nudge_clue_explanation(
    monkeypatch, clean_users_table
):
    _user, token, track_id, mode, levels = await _seed(monkeypatch)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        sid = await _start(client, token, track_id, mode)

        r1 = await client.post(
            f"/api/v1/sessions/{sid}/assistance", cookies={"ic_access": token}
        )
        assert r1.status_code == 200
        assert r1.json()["assistance"]["level"] == 1
        assert r1.json()["assistance"]["assistance_type"] == "nudge"
        assert r1.json()["assistance"]["content"] == "help-level-1"

        r2 = await client.post(
            f"/api/v1/sessions/{sid}/assistance", cookies={"ic_access": token}
        )
        assert r2.status_code == 200
        assert r2.json()["assistance"]["level"] == 2
        assert r2.json()["assistance"]["assistance_type"] == "clue"

        r3 = await client.post(
            f"/api/v1/sessions/{sid}/assistance", cookies={"ic_access": token}
        )
        assert r3.status_code == 200
        assert r3.json()["assistance"]["level"] == 3
        assert r3.json()["assistance"]["assistance_type"] == "explanation"

        r4 = await client.post(
            f"/api/v1/sessions/{sid}/assistance", cookies={"ic_access": token}
        )
        assert r4.status_code == 409

        # Answer after assistance must be marked assisted and events persisted.
        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "Use key-pattern aware TTLs"},
            cookies={"ic_access": token},
        )
        assert r.status_code == 200

    assert levels == [1, 2, 3]
    async with SessionFactory() as db:
        turn = (
            await db.execute(
                select(SessionTurn)
                .where(SessionTurn.session_id == uuid.UUID(sid))
                .order_by(SessionTurn.turn_index)
                .limit(1)
            )
        ).scalar_one()
        assert turn.assisted is True
        assert turn.assistance_level == 3
        assert len(turn.assistance_events) == 3


@pytest.mark.asyncio
async def test_strict_assistance_rejected(monkeypatch, clean_users_table):
    _user, token, track_id, _mode, _levels = await _seed(
        monkeypatch, mode="strict", guided_state="LOCKED"
    )
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        sid = await _start(client, token, track_id, "strict")
        r = await client.post(
            f"/api/v1/sessions/{sid}/assistance", cookies={"ic_access": token}
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_locked_users_cannot_access_guided_sessions(monkeypatch, clean_users_table):
    _user, token, track_id, _mode, _levels = await _seed(
        monkeypatch, guided_state="LOCKED"
    )
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "guided"},
            cookies={"ic_access": token},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_feedback_transcript_marks_assisted_turns(monkeypatch, clean_users_table):
    from app.agents.feedback_agent import FeedbackReportContent
    from app.services import feedback_service

    payloads: list[dict] = []

    async def fake_run(**kwargs):
        payloads.append(kwargs["payload"])
        return FeedbackReportContent(
            session_mode="guided",
            summary_overview="assisted noted",
            coverage_status="PARTIAL",
            question_assessments=[],
            competency_assessments=[
                {
                    "competency_name": "Redis",
                    "assessment_status": "ASSESSED",
                    "level": "developing",
                    "observation": "Used assistance",
                    "confidence": "MEDIUM",
                }
            ],
            strengths=[],
            improvement_areas=["Independent practice"],
            unassessed_topics=[],
            recommendations=["Retry without hints"],
        )

    monkeypatch.setattr("app.services.feedback_service.run_feedback_agent", fake_run)
    _user, token, track_id, mode, _levels = await _seed(monkeypatch)

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        sid = await _start(client, token, track_id, mode)
        await client.post(
            f"/api/v1/sessions/{sid}/assistance", cookies={"ic_access": token}
        )
        await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "after nudge"},
            cookies={"ic_access": token},
        )
        await client.post(
            f"/api/v1/sessions/{sid}/complete", cookies={"ic_access": token}
        )

    async with SessionFactory() as db:
        await feedback_service.process_session_feedback(db, sid)

    assert payloads
    assert payloads[0]["transcript"][0]["assisted"] is True
    assert payloads[0]["transcript"][0]["assistance_level"] == 1
