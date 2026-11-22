"""Fix 3: lifespan Mongo reuse — isolated mocks only, no shared DB writes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from app.api.deps import get_request_mongo, require_admin
from app.db.sqlalchemy import get_db
from app.main import create_app, lifespan


@pytest.mark.asyncio
async def test_get_request_mongo_returns_app_state_mongo_db():
    shared = object()
    request = MagicMock(spec=Request)
    request.app.state.mongo_db = shared
    assert await get_request_mongo(request) is shared


@pytest.mark.asyncio
async def test_get_request_mongo_does_not_construct_motor_client(monkeypatch):
    constructed: list[object] = []

    def boom(*_a, **_k):
        constructed.append(True)
        raise AssertionError("AsyncIOMotorClient must not be constructed per request")

    monkeypatch.setattr("app.db.mongo.AsyncIOMotorClient", boom)
    monkeypatch.setattr(
        "motor.motor_asyncio.AsyncIOMotorClient",
        boom,
        raising=False,
    )

    shared = object()
    request = MagicMock(spec=Request)
    request.app.state.mongo_db = shared
    result = await get_request_mongo(request)
    assert result is shared
    assert constructed == []


@pytest.mark.asyncio
async def test_get_request_mongo_missing_state_returns_503():
    request = MagicMock(spec=Request)
    request.app.state = SimpleNamespace()
    with pytest.raises(HTTPException) as exc_info:
        await get_request_mongo(request)
    assert exc_info.value.status_code == 503
    assert "MongoDB" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_admin_overview_uses_shared_mongo_dependency(monkeypatch):
    shared = object()
    seen: dict[str, object] = {}

    async def fake_overview(db, mongo):
        seen["mongo"] = mongo
        return {
            "users": 1,
            "estimated_cost_usd": 0.0,
            "by_day": [],
            "by_model": [],
        }

    monkeypatch.setattr("app.services.admin_service.overview", fake_overview)

    app = create_app()
    app.state.mongo_db = shared

    async def _admin():
        return SimpleNamespace(email="admin-test@example.com", is_admin=True)

    async def _db():
        yield MagicMock()

    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[get_db] = _db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/overview")

    assert resp.status_code == 200
    assert seen["mongo"] is shared
    body = resp.json()
    assert body["users"] == 1
    assert "estimated_cost_usd" in body


@pytest.mark.asyncio
async def test_admin_overview_503_when_mongo_state_missing(monkeypatch):
    async def fake_overview(db, mongo):
        return {"users": 0, "estimated_cost_usd": 0.0, "by_day": [], "by_model": []}

    monkeypatch.setattr("app.services.admin_service.overview", fake_overview)

    app = create_app()
    # Explicitly no lifespan mongo handle
    if hasattr(app.state, "mongo_db"):
        delattr(app.state, "mongo_db")

    async def _admin():
        return SimpleNamespace(email="admin-test@example.com")

    async def _db():
        yield MagicMock()

    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[get_db] = _db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/overview")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_admin_non_admin_still_403_with_shared_mongo(monkeypatch):
    """Authorization behavior unchanged when mongo is available on app.state."""
    from app.core.config import get_settings
    from app.core.security import create_access_token

    settings = get_settings()
    monkeypatch.setattr(settings, "admin_emails", "real-admin@example.com")

    app = create_app()
    app.state.mongo_db = object()

    # Bypass Postgres user lookup: inject a non-admin current user via override
    from app.api.deps import get_current_user

    async def _user():
        return SimpleNamespace(id="x", email="not-admin@example.com")

    async def _db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token = create_access_token("00000000-0000-0000-0000-000000000099")
        resp = await client.get(
            "/api/v1/admin/overview",
            cookies={"ic_access": token},
        )
    # get_current_user overridden to a non-allow-listed email → require_admin 403
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_lifespan_closes_shared_mongo_client_exactly_once(monkeypatch):
    client = MagicMock()
    db = MagicMock()
    db.onboarding_conversations.create_index = AsyncMock(return_value=None)
    client.__getitem__ = MagicMock(return_value=db)

    monkeypatch.setattr("app.main.get_mongo_client", lambda: client)
    monkeypatch.setattr("app.main.get_s3_client", lambda: MagicMock())
    monkeypatch.setattr(
        "app.main.connect_nats",
        AsyncMock(return_value=None),
    )

    async def _noop_http():
        return MagicMock()

    async def _noop_close():
        return None

    with (
        patch("app.gateway.llm.get_http_client", _noop_http),
        patch("app.gateway.llm.close_http_client", _noop_close),
    ):
        app = FastAPI()
        async with lifespan(app):
            assert app.state.mongo_client is client
            assert app.state.mongo_db is db
        client.close.assert_called_once()
