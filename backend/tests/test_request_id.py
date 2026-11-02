import httpx

from app.main import app


async def test_healthz_returns_request_id_header():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) >= 32


async def test_healthz_echoes_incoming_request_id():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz", headers={"X-Request-ID": "test-trace-123"})
    assert resp.headers["X-Request-ID"] == "test-trace-123"
