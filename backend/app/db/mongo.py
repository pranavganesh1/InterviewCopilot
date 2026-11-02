from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings


def get_mongo_client() -> AsyncIOMotorClient:
    """Return a fresh client. Motor clients bind to the event loop that first
    uses them, so a process-global cached client breaks across loops (tests
    create one loop per test; the API keeps one loop per process via lifespan).
    """
    return AsyncIOMotorClient(get_settings().mongo_url)


def get_mongo_db() -> AsyncIOMotorDatabase:
    return get_mongo_client()[get_settings().mongo_db]
