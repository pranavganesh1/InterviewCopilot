import httpx
import pytest
from pydantic import BaseModel

from app.gateway.llm import LLMGatewayError
from app.gateway.structured import structured_completion


class Out(BaseModel):
    reply: str
    count: int


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_valid_json_parses_first_try():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"reply": "hi", "count": 2}'}}]}
        )

    async with _client(handler) as client:
        out = await structured_completion(client, system="s", user_payload={"x": 1}, schema=Out)
    assert out.reply == "hi"
    assert out.count == 2


@pytest.mark.asyncio
async def test_repairs_after_invalid_json():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = "not json at all" if calls["n"] == 1 else '{"reply": "fixed", "count": 1}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    async with _client(handler) as client:
        out = await structured_completion(client, system="s", user_payload={}, schema=Out)
    assert calls["n"] == 2
    assert out.reply == "fixed"


@pytest.mark.asyncio
async def test_raises_after_second_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "still not json"}}]})

    async with _client(handler) as client:
        with pytest.raises(LLMGatewayError):
            await structured_completion(client, system="s", user_payload={}, schema=Out)
