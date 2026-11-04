"""Task 5: manual /complete must dispatch feedback idempotently."""

import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.track import InterviewBrief, Track
from app.models.user import User


async def _seed_session(monkeypatch, *, complete_on_first_answer: bool = False):
    from app.agents.interviewer import TurnDecision

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"cd-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Networking")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Networking basics",
                    "competencies": [{"name": "TCP", "description": "tcp", "importance": "core"}],
                    "question_areas": [{"topic": "TCP", "guidance": "handshake"}],
                },
            )
        )
        await session.commit()

    async def fake_turn(*args, **kwargs):
        payload = kwargs.get("payload") or (args[0] if args else {})
        if not payload.get("transcript"):
            return TurnDecision(
                evaluation={"coverage": "none", "strengths": [], "gaps": []},
                decision="next_area",
                next_question="Explain the TCP handshake.",
                question_area="TCP",
            )
        if complete_on_first_answer:
            return TurnDecision(
                evaluation={"coverage": "good", "strengths": ["clear"], "gaps": []},
                decision="complete",
                next_question="",
                question_area="TCP",
            )
        return TurnDecision(
            evaluation={"coverage": "partial", "strengths": [], "gaps": ["syn-ack"]},
            decision="follow_up",
            next_question="What does SYN-ACK mean?",
            question_area="TCP",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    return user, create_access_token(str(user.id)), track.id


def _capture_dispatch(monkeypatch):
    published: list[dict] = []

    async def fake_publish(session_id, track_id, user_id, nc=None):
        published.append(
            {
                "session_id": str(session_id),
                "track_id": str(track_id),
                "user_id": str(user_id),
                "nc": nc,
            }
        )

    monkeypatch.setattr("app.services.interview_service.publish_feedback_job", fake_publish)
    return published


@pytest.mark.asyncio
async def test_manual_complete_dispatches_feedback(monkeypatch, clean_users_table):
    user, token, track_id = await _seed_session(monkeypatch)
    published = _capture_dispatch(monkeypatch)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token})
        sid = r.json()["session"]["id"]

        r = await client.post(f"/api/v1/sessions/{sid}/complete", cookies={"ic_access": token})
        assert r.status_code == 200
        assert r.json()["session"]["status"] == "completed"
        assert r.json()["session"]["id"] == sid

    assert len(published) == 1
    assert published[0]["session_id"] == sid
    assert published[0]["track_id"] == str(track_id)
    assert published[0]["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_auto_complete_still_dispatches_feedback(monkeypatch, clean_users_table):
    user, token, track_id = await _seed_session(monkeypatch, complete_on_first_answer=True)
    published = _capture_dispatch(monkeypatch)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token})
        sid = r.json()["session"]["id"]
        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "SYN, SYN-ACK, ACK"},
            cookies={"ic_access": token},
        )
        assert r.status_code == 200
        assert r.json()["completed"] is True

    assert len(published) == 1
    assert published[0]["session_id"] == sid


@pytest.mark.asyncio
async def test_repeated_complete_does_not_duplicate_jobs(monkeypatch, clean_users_table):
    _user, token, track_id = await _seed_session(monkeypatch)
    published = _capture_dispatch(monkeypatch)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token})
        sid = r.json()["session"]["id"]

        r1 = await client.post(f"/api/v1/sessions/{sid}/complete", cookies={"ic_access": token})
        r2 = await client.post(f"/api/v1/sessions/{sid}/complete", cookies={"ic_access": token})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["session"]["status"] == "completed"

    assert len(published) == 1


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_complete_others_session(monkeypatch, clean_users_table):
    _owner, owner_token, track_id = await _seed_session(monkeypatch)
    published = _capture_dispatch(monkeypatch)

    async with SessionFactory() as session:
        other = User(google_sub=f"sub-{uuid.uuid4()}", email=f"other-{uuid.uuid4()}@example.com")
        session.add(other)
        await session.commit()
        await session.refresh(other)
    other_token = create_access_token(str(other.id))

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": owner_token}
        )
        sid = r.json()["session"]["id"]

        r = await client.post(
            f"/api/v1/sessions/{sid}/complete", cookies={"ic_access": other_token}
        )
        assert r.status_code == 404

        # Owner can still complete once.
        r = await client.post(
            f"/api/v1/sessions/{sid}/complete", cookies={"ic_access": owner_token}
        )
        assert r.status_code == 200

    assert len(published) == 1


@pytest.mark.asyncio
async def test_nats_publish_failure_does_not_fail_complete(monkeypatch, clean_users_table):
    """publish_feedback_job never raises; complete must still succeed when NATS is down."""
    _user, token, track_id = await _seed_session(monkeypatch)

    # Force the production publisher path and make NATS connect fail.
    from app.services import events

    monkeypatch.setattr(
        "app.services.interview_service.publish_feedback_job", events.publish_feedback_job
    )
    monkeypatch.setattr(
        "app.services.events.nats.connect",
        AsyncMock(side_effect=ConnectionError("refused")),
    )

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token})
        sid = r.json()["session"]["id"]
        r = await client.post(f"/api/v1/sessions/{sid}/complete", cookies={"ic_access": token})
        assert r.status_code == 200
        assert r.json()["session"]["status"] == "completed"
