import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.gateway.llm import LLMGatewayError, chat_completion


@pytest.mark.asyncio
async def test_chat_completion_returns_content_and_logs():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Bearer " in request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Hello!"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )

    mongo_db = AsyncMongoMockClient()["testdb"]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        content = await chat_completion(
            client,
            model="interview-chat",
            messages=[{"role": "user", "content": "hi"}],
            mongo_db=mongo_db,
            request_id="req-1",
        )
    assert content == "Hello!"
    log = await mongo_db.llm_call_logs.find_one({"request_id": "req-1"})
    assert log is not None
    assert log["total_tokens"] == 7
    assert log["model"] == "interview-chat"


@pytest.mark.asyncio
async def test_chat_completion_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMGatewayError):
            await chat_completion(
                client,
                model="interview-chat",
                messages=[{"role": "user", "content": "hi"}],
            )
