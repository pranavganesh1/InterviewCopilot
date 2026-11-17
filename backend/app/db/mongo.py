from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings


def get_mongo_client() -> AsyncIOMotorClient:
    """Return a fresh client for lifespan startup or isolated tests.

    Motor clients bind to the event loop that first uses them, so a
    process-global cached client breaks across loops (tests create one loop
    per test; the API keeps one loop per process via lifespan).

    Request handlers must use ``app.state.mongo_db`` via
    ``app.api.deps.get_request_mongo`` — never open a client per request.
    """
    return AsyncIOMotorClient(get_settings().mongo_url)


def get_mongo_db() -> AsyncIOMotorDatabase:
    """Open a fresh client+DB (tests / tooling only — not for FastAPI Depends)."""
    return get_mongo_client()[get_settings().mongo_db]
