import uuid

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.user import User


@pytest.mark.asyncio
async def test_user_roundtrip(clean_users_table):
    async with SessionFactory() as session:
        user = User(
            google_sub=f"sub-{uuid.uuid4()}",
            email=f"t-{uuid.uuid4()}@example.com",
            name="T",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.id is not None
        assert user.created_at is not None
