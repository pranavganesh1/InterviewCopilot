import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User


@pytest.mark.asyncio
async def test_chat_creates_vault_items_and_replies(monkeypatch, clean_users_table):
    from sqlalchemy import select

    from app.agents.onboarding import ExtractedItem, OnboardingTurn
    from app.db.mongo import get_mongo_client
    from app.models.vault import VaultItem

    email = f"o-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))

    turn = OnboardingTurn(
        reply="Great, tell me about your stack!",
        extracted_items=[
            ExtractedItem(category="project", title="Line follower robot", details={"role": "solo"})
        ],
    )

    async def fake_turn(*args, **kwargs):
        return turn

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", fake_turn)

    app = create_app()
    from app.core.config import get_settings

    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "I built a line follower robot solo"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "stack" in body["reply"]
    assert body["items_created"][0]["title"] == "Line follower robot"

    async with SessionFactory() as session:
        items = (
            (await session.execute(select(VaultItem).where(VaultItem.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(items) == 1 and items[0].source == "onboarding_chat"

    mongo_db = get_mongo_client()["interviewcopilot"]
    await mongo_db.onboarding_conversations.delete_many({"user_id": str(user.id)})


@pytest.mark.asyncio
async def test_onboarding_requires_auth():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/onboarding/chat", json={"message": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_onboarding_state_reports_completion(clean_users_table):
    from app.db.mongo import get_mongo_client
    from app.models.vault import VaultItem

    email = f"oc-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        for cat, title in (
            ("project", "P"),
            ("skill", "S"),
            ("education", "E"),
        ):
            session.add(
                VaultItem(
                    user_id=user.id,
                    category=cat,
                    title=title,
                    details={},
                    source="onboarding_chat",
                )
            )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    app = create_app()
    from app.core.config import get_settings

    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/onboarding/state",
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["onboarding_complete"] is True
    assert body["onboarding_finished"] is False
    assert body["missing_categories"] == []

    mongo_db = get_mongo_client()[get_settings().mongo_db]
    await mongo_db.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_complete_marks_finished_and_survives_state_reload(clean_users_table):
    from sqlalchemy import select

    from app.db.mongo import get_mongo_client
    from app.models.vault import VaultItem

    email = f"of-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        for cat, title in (
            ("project", "P"),
            ("skill", "S"),
            ("education", "E"),
        ):
            session.add(
                VaultItem(
                    user_id=user.id,
                    category=cat,
                    title=title,
                    details={},
                    source="onboarding_chat",
                )
            )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = user.id

    app = create_app()
    from app.core.config import get_settings

    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/onboarding/complete",
            cookies={"ic_access": token},
        )
        assert first.status_code == 200
        body = first.json()
        assert body["onboarding_finished"] is True
        assert body["onboarding_complete"] is True
        assert body["onboarding_completed_at"] is not None

        again = await client.post(
            "/api/v1/onboarding/complete",
            cookies={"ic_access": token},
        )
        assert again.status_code == 200
        assert again.json()["onboarding_finished"] is True

        state = await client.get(
            "/api/v1/onboarding/state",
            cookies={"ic_access": token},
        )
        assert state.status_code == 200
        assert state.json()["onboarding_finished"] is True
        assert state.json()["missing_categories"] == []

        me = await client.get("/api/v1/auth/me", cookies={"ic_access": token})
        assert me.status_code == 200
        assert me.json()["onboarding_completed"] is True

    async with SessionFactory() as session:
        refreshed = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        assert refreshed.onboarding_completed_at is not None


@pytest.mark.asyncio
async def test_complete_rejects_incomplete_vault(clean_users_table):
    email = f"oi-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        token = create_access_token(str(user.id))

    app = create_app()
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client

    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/complete",
            cookies={"ic_access": token},
        )
    assert resp.status_code == 409
