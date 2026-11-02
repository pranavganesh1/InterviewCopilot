import os

# Tests run against a dedicated database so fixture cleanup never touches
# real data. Must be set before any app module imports config (lru_cache).
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://interview:interview@localhost:5432/interviewcopilot_test"
)

import pytest  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db.sqlalchemy import SessionFactory  # noqa: E402
from app.models.interview import InterviewSession, SessionTurn  # noqa: E402
from app.models.track import InterviewBrief, Track  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vault import VaultItem  # noqa: E402


@pytest.fixture
async def clean_users_table():
    """Remove vault items and users after a DB-touching test (test DB only)."""
    yield
    async with SessionFactory() as session:
        await session.execute(delete(SessionTurn))
        await session.execute(delete(InterviewSession))
        await session.execute(delete(InterviewBrief))
        await session.execute(delete(Track))
        await session.execute(delete(VaultItem))
        await session.execute(delete(User))
        await session.commit()
