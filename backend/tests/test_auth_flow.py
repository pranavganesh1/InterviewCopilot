import uuid

import httpx
import pytest

from app.main import create_app


@pytest.mark.asyncio
async def test_google_url_returns_accounts_google():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/google/url")
    assert resp.status_code == 200
    assert "accounts.google.com" in resp.json()["url"]


@pytest.mark.asyncio
async def test_me_requires_auth():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_callback_upserts_user_and_sets_cookies(monkeypatch, clean_users_table):
    from sqlalchemy import select

    from app.db.sqlalchemy import SessionFactory
    from app.models.user import User

    email = f"student-{uuid.uuid4()}@example.com"

    async def fake_exchange(request):
        return {
            "userinfo": {
                "sub": f"google-sub-{uuid.uuid4()}",
                "email": email,
                "name": "Student",
                "picture": "https://example.com/p.png",
            }
        }

    app = create_app()
    monkeypatch.setattr(app.state.oauth.google, "authorize_access_token", fake_exchange)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/google/callback?code=abc&state=xyz")
    assert resp.status_code == 200
    assert "ic_access" in resp.cookies and "ic_refresh" in resp.cookies

    async with SessionFactory() as session:
        found = (await session.execute(select(User).where(User.email == email))).scalar_one()
        assert found.google_sub.startswith("google-sub-")
