import pytest
from sqlalchemy import delete

from app.db.sqlalchemy import SessionFactory
from app.models.user import User
from app.models.vault import VaultItem


@pytest.fixture
async def clean_users_table():
    """Remove vault items and users after a DB-touching test so reruns stay idempotent."""
    yield
    async with SessionFactory() as session:
        await session.execute(delete(VaultItem))
        await session.execute(delete(User))
        await session.commit()
