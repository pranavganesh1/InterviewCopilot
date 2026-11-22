import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

# Application database name — never use this from pytest.
APP_MONGO_DB = "interviewcopilot"
TEST_MONGO_DB = "interviewcopilot_test"


def assert_mongo_db_safe_for_tests(name: str) -> str:
    """Block the shared application Mongo DB name while pytest is running."""
    if os.environ.get("PYTEST_CURRENT_TEST") and name == APP_MONGO_DB:
        raise RuntimeError(
            f"Refusing Mongo DB {name!r} during pytest; "
            f"use dedicated test database {TEST_MONGO_DB!r}."
        )
    return name


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
    """Open a fresh client+DB (tests / tooling only — not for FastAPI Depends).

    Under pytest, refuses the application database name ``interviewcopilot``.
    """
    name = assert_mongo_db_safe_for_tests(get_settings().mongo_db)
    return get_mongo_client()[name]
