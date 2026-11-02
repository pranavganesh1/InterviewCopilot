import uuid

import pytest

from app.db.mongo import get_mongo_client
from app.db.sqlalchemy import SessionFactory
from app.models.user import User
from app.models.vault import VaultItem
from app.services.conversation_store import append_message, get_messages


@pytest.mark.asyncio
async def test_vault_item_roundtrip(clean_users_table):
    async with SessionFactory() as session:
        user = User(
            google_sub=f"sub-{uuid.uuid4()}",
            email=f"v-{uuid.uuid4()}@example.com",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        item = VaultItem(
            user_id=user.id,
            category="project",
            title="Recommender system",
            details={"role": "solo", "stack": "python"},
            source="onboarding_chat",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        assert item.id is not None
        assert item.details["role"] == "solo"


@pytest.mark.asyncio
async def test_conversation_append_and_read():
    mongo_db = get_mongo_client()["interviewcopilot_test"]
    user_id = str(uuid.uuid4())
    await mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
    await append_message(mongo_db, user_id, "user", "I built a robot")
    await append_message(mongo_db, user_id, "assistant", "Tell me more")
    msgs = await get_messages(mongo_db, user_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    await mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
