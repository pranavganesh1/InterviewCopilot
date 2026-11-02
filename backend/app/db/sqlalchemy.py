from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

# NullPool: each session gets a fresh connection. Avoids cross-event-loop
# connection reuse bugs (tests create a loop per test; the feedback worker
# will run its own loop) and is negligible for this product's traffic.
engine = create_async_engine(get_settings().database_url, poolclass=pool.NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with SessionFactory() as session:
        yield session
