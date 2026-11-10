"""GET /me/open-sessions: unfinished interviews for the dashboard."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import Track
from app.models.user import User


async def _user(prefix: str = "open") -> tuple[User, str]:
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"{prefix}-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, create_access_token(str(user.id))


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_open_sessions_empty_for_new_user(clean_users_table):
    from app.main import create_app

    _user_row, token = await _user()
    app = create_app()
    async with _client(app) as client:
        resp = await client.get("/api/v1/me/open-sessions", cookies={"ic_access": token})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_open_sessions_lists_owner_progress_and_excludes_archived(clean_users_table):
    from app.main import create_app

    owner, owner_token = await _user("owner")
    other, other_token = await _user("other")

    async with SessionFactory() as session:
        active = Track(user_id=owner.id, track_type="topic", subject="Graphs")
        archived = Track(user_id=owner.id, track_type="topic", subject="Trees")
        foreign = Track(user_id=other.id, track_type="topic", subject="Foreign")
        session.add_all([active, archived, foreign])
        await session.commit()
        await session.refresh(active)
        await session.refresh(archived)
        await session.refresh(foreign)

        archived.archived_at = datetime.now(UTC)
        open_active = InterviewSession(
            track_id=active.id, user_id=owner.id, mode="strict", status="in_progress"
        )
        open_archived = InterviewSession(
            track_id=archived.id, user_id=owner.id, mode="guided", status="in_progress"
        )
        open_other = InterviewSession(
            track_id=foreign.id, user_id=other.id, mode="strict", status="in_progress"
        )
        done = InterviewSession(
            track_id=active.id, user_id=owner.id, mode="strict", status="completed"
        )
        session.add_all([open_active, open_archived, open_other, done])
        await session.commit()
        await session.refresh(open_active)

        session.add(
            SessionTurn(
                session_id=open_active.id,
                turn_index=1,
                question_area="Graphs",
                question="What is BFS?",
                answer="Level order.",
            )
        )
        session.add(
            SessionTurn(
                session_id=open_active.id,
                turn_index=2,
                question_area="Graphs",
                question="What is DFS?",
                answer=None,
            )
        )
        await session.commit()
        active_id = str(active.id)
        session_id = str(open_active.id)

    app = create_app()
    async with _client(app) as client:
        mine = await client.get(
            "/api/v1/me/open-sessions", cookies={"ic_access": owner_token}
        )
        assert mine.status_code == 200
        body = mine.json()
        assert len(body) == 1
        row = body[0]
        assert row["session_id"] == session_id
        assert row["track_id"] == active_id
        assert row["track_subject"] == "Graphs"
        assert row["mode"] == "strict"
        assert row["status"] == "in_progress"
        assert row["answered_count"] == 1
        assert row["question_index"] == 2
        assert row["max_turns"] >= 1
        assert "duration_minutes" in row
        assert "created_at" in row

        theirs = await client.get(
            "/api/v1/me/open-sessions", cookies={"ic_access": other_token}
        )
        assert theirs.status_code == 200
        assert len(theirs.json()) == 1
        assert theirs.json()[0]["track_subject"] == "Foreign"


@pytest.mark.asyncio
async def test_open_sessions_requires_auth(clean_users_table):
    from app.main import create_app

    app = create_app()
    async with _client(app) as client:
        resp = await client.get("/api/v1/me/open-sessions")
    assert resp.status_code == 401
