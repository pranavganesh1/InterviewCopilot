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
