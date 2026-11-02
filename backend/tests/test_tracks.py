import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User


async def _create_user() -> tuple[User, str]:
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"tr-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, create_access_token(str(user.id))


def _fake_brief_payload():
    return {
        "summary": "DSA interview with focus on arrays and hashing",
        "preparation_plan": ["Revise hashing", "Practice two-pointer problems"],
        "competencies": [
            {"name": "Arrays", "description": "Array manipulation", "importance": "core"}
        ],
        "question_areas": [{"topic": "Hashmaps", "guidance": "trade-offs of hash collisions"}],
        "candidate_angle_notes": "Probe the recommendation-system project for DS choices.",
    }


@pytest.mark.asyncio
async def test_create_track_generates_brief_v1(monkeypatch, clean_users_table):
    from app.agents.track_creator import InterviewBriefContent

    user, token = await _create_user()
    content = InterviewBriefContent.model_validate(_fake_brief_payload())

    async def fake_turn(*args, **kwargs):
        return content

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tracks",
            json={"track_type": "topic", "subject": "Data Structures & Algorithms"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["track"]["subject"] == "Data Structures & Algorithms"
    assert body["brief"]["version"] == 1
    assert body["brief"]["content"]["summary"].startswith("DSA interview")


@pytest.mark.asyncio
async def test_company_jd_requires_jd_text(clean_users_table):
    user, token = await _create_user()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tracks",
            json={"track_type": "company_jd", "subject": "SDE Intern", "company": "Acme"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tracks_require_auth():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/tracks")
    assert resp.status_code == 401
