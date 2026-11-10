"""Idempotent start, concurrent safety, empty-session cleanup (no deletes)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.services import interview_service


async def _setup(monkeypatch):
    from app.agents.interviewer import TurnDecision

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"dedupe-{uuid.uuid4()}@ex.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Arrays")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "arrays",
                    "competencies": [],
                    "question_areas": [{"topic": "Arrays", "guidance": "basics"}],
                },
            )
        )
        await session.commit()

    async def fake_turn(*args, **kwargs):
        return TurnDecision(
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            decision="next_area",
            next_question="What is an array?",
            question_area="Arrays",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    return user, create_access_token(str(user.id)), track.id


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


async def _open_count(track_id) -> int:
    async with SessionFactory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(InterviewSession)
            .where(
                InterviewSession.track_id == track_id,
                InterviewSession.status == "in_progress",
            )
        )
        return int(result.scalar_one())


@pytest.mark.asyncio
async def test_second_start_returns_existing_empty_session(monkeypatch, clean_users_table):
    _user, token, track_id = await _setup(monkeypatch)
    app = create_app()
    async with _client(app) as client:
        first = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "duration_minutes": 60},
            cookies={"ic_access": token},
        )
        assert first.status_code == 201
        sid = first.json()["session"]["id"]
        second = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "duration_minutes": 60},
            cookies={"ic_access": token},
        )
        assert second.status_code == 201
        assert second.json()["session"]["id"] == sid
        assert second.json()["turn"]["question"]
    assert await _open_count(track_id) == 1


@pytest.mark.asyncio
async def test_concurrent_starts_create_one_session(monkeypatch, clean_users_table):
    _user, token, track_id = await _setup(monkeypatch)
    app = create_app()
    async with _client(app) as client:

        async def _start():
            return await client.post(
                f"/api/v1/tracks/{track_id}/sessions",
                json={"mode": "strict", "duration_minutes": 45},
                cookies={"ic_access": token},
            )

        a, b = await asyncio.gather(_start(), _start())
        assert a.status_code == 201
        assert b.status_code == 201
        assert a.json()["session"]["id"] == b.json()["session"]["id"]
    assert await _open_count(track_id) == 1


@pytest.mark.asyncio
async def test_session_with_answers_is_not_reused(monkeypatch, clean_users_table):
    _user, token, track_id = await _setup(monkeypatch)
    app = create_app()
    async with _client(app) as client:
        started = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "duration_minutes": 60},
            cookies={"ic_access": token},
        )
        sid = started.json()["session"]["id"]
        answered = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "A contiguous block of memory."},
            cookies={"ic_access": token},
        )
        assert answered.status_code == 200
        again = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "duration_minutes": 60},
            cookies={"ic_access": token},
        )
        assert again.status_code == 409
    assert await _open_count(track_id) == 1


@pytest.mark.asyncio
async def test_open_session_list_newest_first_and_limit(monkeypatch, clean_users_table):
    user, token, track_id = await _setup(monkeypatch)
    async with SessionFactory() as session:
        older = InterviewSession(
            track_id=track_id,
            user_id=user.id,
            mode="strict",
            status="in_progress",
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        newer = InterviewSession(
            track_id=track_id,
            user_id=user.id,
            mode="guided",
            status="in_progress",
            created_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        session.add_all([older, newer])
        await session.commit()
        await session.refresh(older)
        await session.refresh(newer)
        for row in (older, newer):
            session.add(
                SessionTurn(
                    session_id=row.id,
                    turn_index=1,
                    question_area="Arrays",
                    question="Q?",
                    answer=None,
                )
            )
        await session.commit()
        newer_id = str(newer.id)

    app = create_app()
    async with _client(app) as client:
        resp = await client.get(
            f"/api/v1/tracks/{track_id}/open-session?limit=1",
            cookies={"ic_access": token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session"]["id"] == newer_id
        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["id"] == newer_id

        mine = await client.get(
            "/api/v1/me/open-sessions?limit=1",
            cookies={"ic_access": token},
        )
        assert mine.status_code == 200
        assert len(mine.json()) == 1
        assert mine.json()[0]["session_id"] == newer_id


@pytest.mark.asyncio
async def test_close_empty_script_dry_run_and_apply(monkeypatch, clean_users_table):
    user, _token, track_id = await _setup(monkeypatch)
    async with SessionFactory() as session:
        stale = InterviewSession(
            track_id=track_id,
            user_id=user.id,
            mode="strict",
            status="in_progress",
            created_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        fresh = InterviewSession(
            track_id=track_id,
            user_id=user.id,
            mode="strict",
            status="in_progress",
            created_at=datetime.now(UTC) - timedelta(minutes=2),
        )
        with_answer = InterviewSession(
            track_id=track_id,
            user_id=user.id,
            mode="strict",
            status="in_progress",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        session.add_all([stale, fresh, with_answer])
        await session.commit()
        await session.refresh(stale)
        await session.refresh(fresh)
        await session.refresh(with_answer)
        session.add(
            SessionTurn(
                session_id=stale.id,
                turn_index=1,
                question_area="Arrays",
                question="stale?",
                answer=None,
            )
        )
        session.add(
            SessionTurn(
                session_id=fresh.id,
                turn_index=1,
                question_area="Arrays",
                question="fresh?",
                answer=None,
            )
        )
        session.add(
            SessionTurn(
                session_id=with_answer.id,
                turn_index=1,
                question_area="Arrays",
                question="answered?",
                answer="yes",
            )
        )
        await session.commit()
        stale_id = stale.id
        before_turns = (
            await session.execute(select(func.count()).select_from(SessionTurn))
        ).scalar_one()
        before_sessions = (
            await session.execute(select(func.count()).select_from(InterviewSession))
        ).scalar_one()

    async with SessionFactory() as db:
        eligible = await interview_service.find_empty_sessions_for_cleanup(
            db, older_than_minutes=10
        )
        assert {row.id for row in eligible} == {stale_id}
        # Dry-run path: no apply
        assert all(row.status == "in_progress" for row in eligible)

    async with SessionFactory() as db:
        closed = await interview_service.abort_sessions_by_ids(db, [stale_id])
        assert closed == 1

    async with SessionFactory() as session:
        row = await session.get(InterviewSession, stale_id)
        assert row is not None
        assert row.status == "aborted"
        after_turns = (
            await session.execute(select(func.count()).select_from(SessionTurn))
        ).scalar_one()
        after_sessions = (
            await session.execute(select(func.count()).select_from(InterviewSession))
        ).scalar_one()
        assert after_turns == before_turns
        assert after_sessions == before_sessions
        still_open = await _open_count(track_id)
        assert still_open == 2


@pytest.mark.asyncio
async def test_close_empty_sessions_endpoint(monkeypatch, clean_users_table):
    user, token, track_id = await _setup(monkeypatch)
    async with SessionFactory() as session:
        empty = InterviewSession(
            track_id=track_id, user_id=user.id, mode="strict", status="in_progress"
        )
        session.add(empty)
        await session.commit()
        await session.refresh(empty)
        session.add(
            SessionTurn(
                session_id=empty.id,
                turn_index=1,
                question_area="Arrays",
                question="Q",
                answer=None,
            )
        )
        await session.commit()
        empty_id = str(empty.id)

    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            f"/api/v1/tracks/{track_id}/close-empty-sessions",
            cookies={"ic_access": token},
        )
        assert resp.status_code == 200
        assert resp.json()["closed_count"] == 1
        assert empty_id in resp.json()["session_ids"]
        open_resp = await client.get(
            f"/api/v1/tracks/{track_id}/open-session",
            cookies={"ic_access": token},
        )
        assert open_resp.json()["session"] is None
        assert open_resp.json()["sessions"] == []
