import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.models.user import User


@pytest.fixture
def admin_env(monkeypatch):
    """Point ADMIN_EMAILS at a known address for this test."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "admin_emails", "admin-test@example.com")


async def _make_user(prefix: str = "u") -> tuple[User, str]:
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"{prefix}-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, create_access_token(str(user.id))


ADMIN_PATHS = [
    "/api/v1/admin/overview",
    "/api/v1/admin/users",
    "/api/v1/admin/users/00000000-0000-0000-0000-000000000001",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_PATHS)
async def test_admin_endpoints_401_when_logged_out(path):
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_PATHS)
async def test_admin_endpoints_403_for_non_admin(admin_env, clean_users_table, path):
    _user, token = await _make_user("nonadmin")
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path, cookies={"ic_access": token})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overview_403_for_non_admin(admin_env, clean_users_table):
    user, token = await _make_user("nonadmin")
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/admin/overview", cookies={"ic_access": token})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_overview_counts_and_cost(admin_env, clean_users_table):
    from app.main import create_app

    # The admin user (email matches ADMIN_EMAILS)
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email="admin-test@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token(str(user.id))

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/admin/overview", cookies={"ic_access": token})
    assert r.status_code == 200
    body = r.json()
    assert body["users"] >= 1
    assert "estimated_cost_usd" in body
    assert "by_day" in body and "by_model" in body
