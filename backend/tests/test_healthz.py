"""Liveness and readiness probes — mocked deps only, no shared infrastructure."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.main import app, collect_readyz_checks, create_app


async def test_healthz_returns_ok():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_healthz_ok_when_dependencies_unavailable(monkeypatch):
    """Liveness must not require Postgres/Mongo/NATS/LiteLLM/S3."""

    async def boom_collect(_app, *, litellm_url: str):
        raise RuntimeError("deps down")

    monkeypatch.setattr("app.main.collect_readyz_checks", boom_collect)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def _ok_payload() -> dict[str, str]:
    return {
        "postgres": "ok",
        "mongo": "ok",
        "nats": "ok",
        "litellm": "ok",
        "s3": "ok",
    }


@pytest.fixture
def readyz_app(monkeypatch):
    """App with mocked dependency probes; ASGI client hits /readyz only."""
    test_app = create_app()

    async def fake_collect(_app, *, litellm_url: str):
        return dict(getattr(test_app.state, "_readyz_override", _ok_payload()))

    monkeypatch.setattr("app.main.collect_readyz_checks", fake_collect)
    return test_app


async def _get_readyz(test_app):
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/readyz")


async def test_readyz_all_healthy_returns_200(readyz_app):
    readyz_app.state._readyz_override = _ok_payload()
    resp = await _get_readyz(readyz_app)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"] == _ok_payload()


@pytest.mark.parametrize(
    "failed_key",
    ["postgres", "mongo", "nats", "litellm", "s3"],
)
async def test_readyz_single_dependency_failure_returns_503(readyz_app, failed_key):
    checks = _ok_payload()
    checks[failed_key] = "disconnected" if failed_key == "nats" else "error: TimeoutError"
    readyz_app.state._readyz_override = checks
    resp = await _get_readyz(readyz_app)
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"][failed_key] != "ok"
    assert "mongo" in body["checks"]
    assert "s3" in body["checks"]


async def test_readyz_response_never_exposes_secrets(readyz_app):
    secret = "mongodb://user:hunter2@mongo:27017/interviewcopilot"
    s3_secret = "aws_secret_access_key=supersecret"
    readyz_app.state._readyz_override = {
        "postgres": "error: OperationalError",
        "mongo": "error: ServerSelectionTimeoutError",
        "nats": "disconnected",
        "litellm": "error: ConnectError",
        "s3": "error: ClientError",
    }
    resp = await _get_readyz(readyz_app)
    raw = resp.text
    assert secret not in raw
    assert s3_secret not in raw
    assert "hunter2" not in raw
    assert "supersecret" not in raw
    assert "mongodb://" not in raw
    body = resp.json()
    for value in body["checks"].values():
        assert "://" not in value
        assert "password" not in value.lower()
        assert "secret" not in value.lower()


async def test_collect_readyz_checks_uses_lifespan_mongo_and_s3(monkeypatch):
    """Probes call app.state mongo ping + s3 head_bucket; no shared DB writes."""
    test_app = create_app()
    mongo_db = AsyncMock()
    mongo_db.command = AsyncMock(return_value={"ok": 1})
    test_app.state.mongo_db = mongo_db
    test_app.state.nats = SimpleNamespace(is_connected=True)
    s3 = MagicMock()
    s3.head_bucket = MagicMock(return_value={"ResponseMetadata": {"HTTPStatusCode": 200}})
    test_app.state.s3 = s3

    class _Session:
        async def execute(self, *_a, **_k):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

    monkeypatch.setattr("app.main.SessionFactory", lambda: _Session())

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def get(self, url):
            assert "liveliness" in url
            assert "sk-" not in url
            return _Resp()

    monkeypatch.setattr("app.main.httpx.AsyncClient", _Client)

    checks = await collect_readyz_checks(test_app, litellm_url="http://litellm.test")
    assert checks == _ok_payload()
    mongo_db.command.assert_awaited_once_with("ping")
    s3.head_bucket.assert_called_once_with(Bucket="resumes")


async def test_collect_readyz_mongo_failure(monkeypatch):
    test_app = create_app()
    mongo_db = AsyncMock()
    mongo_db.command = AsyncMock(side_effect=ConnectionError("mongodb://user:hunter2@host/db"))
    test_app.state.mongo_db = mongo_db
    test_app.state.nats = SimpleNamespace(is_connected=True)
    test_app.state.s3 = MagicMock()
    test_app.state.s3.head_bucket = MagicMock(return_value={})

    class _Session:
        async def execute(self, *_a, **_k):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

    monkeypatch.setattr("app.main.SessionFactory", lambda: _Session())

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def get(self, *_a, **_k):
            return _Resp()

    monkeypatch.setattr("app.main.httpx.AsyncClient", _Client)

    checks = await collect_readyz_checks(test_app, litellm_url="http://litellm.test")
    assert checks["mongo"] == "error: ConnectionError"
    assert "hunter2" not in checks["mongo"]
    assert checks["postgres"] == "ok"


async def test_collect_readyz_s3_failure(monkeypatch):
    test_app = create_app()
    mongo_db = AsyncMock()
    mongo_db.command = AsyncMock(return_value={"ok": 1})
    test_app.state.mongo_db = mongo_db
    test_app.state.nats = SimpleNamespace(is_connected=True)
    s3 = MagicMock()
    s3.head_bucket = MagicMock(
        side_effect=RuntimeError("endpoint=http://seaweed:8333 key=local secret=local")
    )
    test_app.state.s3 = s3

    class _Session:
        async def execute(self, *_a, **_k):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

    monkeypatch.setattr("app.main.SessionFactory", lambda: _Session())

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def get(self, *_a, **_k):
            return _Resp()

    monkeypatch.setattr("app.main.httpx.AsyncClient", _Client)

    checks = await collect_readyz_checks(test_app, litellm_url="http://litellm.test")
    assert checks["s3"] == "error: RuntimeError"
    assert "secret=local" not in checks["s3"]
    assert "8333" not in checks["s3"]
