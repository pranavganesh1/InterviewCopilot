import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.feedback import FeedbackReport, ProgressionState
from app.models.interview import InterviewSession
from app.models.track import Track
from app.models.user import User


async def _setup_completed_session_with_report():
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"fr-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        s = InterviewSession(track_id=track.id, user_id=user.id, mode="strict", status="completed")
        session.add(s)
        await session.commit()
        await session.refresh(s)
        session.add(
            FeedbackReport(
                session_id=s.id,
                track_id=track.id,
                user_id=user.id,
                content={"summary_overview": "Did well.", "coverage_status": "PARTIAL"},
            )
        )
        session.add(ProgressionState(track_id=track.id, strict_completed=1, guided_state="LOCKED"))
        await session.commit()
        return user.id, s.id, track.id


@pytest.mark.asyncio
async def test_report_route(clean_users_table):
    from app.core.config import get_settings

    user_id, session_id, _ = await _setup_completed_session_with_report()
    app = create_app()
    from app.db.mongo import get_mongo_client

    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/api/v1/sessions/{session_id}/report",
            cookies={"ic_access": create_access_token(str(user_id))},
        )
    assert r.status_code == 200
    assert r.json()["content"]["summary_overview"] == "Did well."


@pytest.mark.asyncio
async def test_report_404_when_missing(clean_users_table):
    from app.core.config import get_settings

    user_id, session_id, _ = await _setup_completed_session_with_report()
    async with SessionFactory() as session:
        # delete the report to simulate the worker not having run yet
        from sqlalchemy import delete

        await session.execute(delete(FeedbackReport))
        await session.commit()

    app = create_app()
    from app.db.mongo import get_mongo_client

    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/api/v1/sessions/{session_id}/report",
            cookies={"ic_access": create_access_token(str(user_id))},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_progression_route(clean_users_table):
    from app.core.config import get_settings

    user_id, _, track_id = await _setup_completed_session_with_report()
    app = create_app()
    from app.db.mongo import get_mongo_client

    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/api/v1/tracks/{track_id}/progression",
            cookies={"ic_access": create_access_token(str(user_id))},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["strict_completed"] == 1
    assert body["guided_state"] == "LOCKED"


@pytest.mark.asyncio
async def test_report_requires_auth():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/api/v1/sessions/{uuid.uuid4()}/report")
    assert r.status_code == 401
