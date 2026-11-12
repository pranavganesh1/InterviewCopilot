import json

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.gateway.llm import (
    LLMCause,
    LLMGatewayError,
    chat_completion,
    classify_http_failure,
    clear_model_cooldowns,
)
from app.gateway.structured import gemini_safe_schema


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    clear_model_cooldowns()
    yield
    clear_model_cooldowns()


def test_classify_http_failure_mapping():
    assert (
        classify_http_failure(429, provider_code="RESOURCE_EXHAUSTED")
        == LLMCause.rate_limited
    )
    assert classify_http_failure(503, provider_code="overloaded") == LLMCause.overloaded
    assert (
        classify_http_failure(404, provider_code="model_not_found")
        == LLMCause.model_not_found
    )
    assert classify_http_failure(401, provider_code="invalid_api_key") == LLMCause.auth_failed
    assert (
        classify_http_failure(400, provider_code="Invalid schema additionalProperties")
        == LLMCause.schema_rejected
    )
    assert classify_http_failure(None, exc=httpx.TimeoutException("t")) == LLMCause.timeout


def test_gemini_safe_schema_drops_unsupported():
    raw = {
        "type": "object",
        "additionalProperties": False,
        "$defs": {"X": {"type": "string"}},
        "properties": {
            "reply": {"type": "string", "title": "Reply"},
            "items": {"$ref": "#/$defs/X"},
        },
    }
    safe = gemini_safe_schema(raw)
    assert "additionalProperties" not in safe
    assert "$defs" not in safe
    assert "properties" in safe
    assert "$ref" not in json.dumps(safe)


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
async def test_primary_failure_uses_fallback_model():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["model"])
        if body["model"] == "structured-json":
            return httpx.Response(503, json={"error": "quota"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "coverage": "partial",
                                    "strengths": [],
                                    "gaps": ["missing a concrete example"],
                                    "expected_answer_explanation": "Name the mechanism.",
                                    "corrected_code": "",
                                    "time_complexity": "",
                                    "space_complexity": "",
                                }
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            },
        )

    from app.agents.interviewer import AnswerEvaluation
    from app.gateway.llm import llm_model_used
    from app.gateway.structured import structured_completion

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await structured_completion(
            client,
            system="Score the answer.",
            user_payload={"last_answer": "hashing spreads keys across buckets"},
            schema=AnswerEvaluation,
            model="structured-json",
            temperature=0,
        )
    assert isinstance(result, AnswerEvaluation)
    assert result.coverage == "partial"
    assert seen == ["structured-json", "structured-json-nim"]
    assert llm_model_used.get() == "structured-json-nim"


@pytest.mark.asyncio
async def test_chat_completion_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMGatewayError) as ei:
            await chat_completion(
                client,
                model="interview-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_attempts=1,
            )
        # Primary + fallbacks all 500 → unknown/overloaded style cause
        assert ei.value.status_code == 500


@pytest.mark.asyncio
async def test_rate_limited_surfaces_retry_after_and_cause():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "12"},
            json={"error": {"code": "RESOURCE_EXHAUSTED", "message": "quota"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMGatewayError) as ei:
            await chat_completion(
                client,
                model="structured-json-gemini",
                messages=[{"role": "user", "content": "hi"}],
                max_attempts=1,
            )
    assert ei.value.cause == LLMCause.rate_limited
    assert ei.value.status_code == 429
    assert ei.value.retry_after_seconds == 12.0
    assert ei.value.provider_code == "RESOURCE_EXHAUSTED"


@pytest.mark.asyncio
async def test_rate_limited_falls_back_then_succeeds():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["model"])
        if body["model"] == "structured-json":
            return httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"error": {"code": "RESOURCE_EXHAUSTED"}},
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        content = await chat_completion(
            client,
            model="structured-json",
            messages=[{"role": "user", "content": "hi"}],
            max_attempts=1,
        )
    assert content == "ok"
    assert seen[0] == "structured-json"
    assert seen[1] == "structured-json-nim"


@pytest.mark.asyncio
async def test_cooldown_skips_failing_deployment_next_request():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["model"])
        if body["model"] == "structured-json":
            return httpx.Response(429, json={"error": {"code": "RESOURCE_EXHAUSTED"}})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await chat_completion(
            client,
            model="structured-json",
            messages=[{"role": "user", "content": "hi"}],
            max_attempts=1,
        )
        seen.clear()
        await chat_completion(
            client,
            model="structured-json",
            messages=[{"role": "user", "content": "hi again"}],
            max_attempts=1,
        )
    # Second request should skip cooled-down primary.
    assert "structured-json" not in seen
    assert seen[0] == "structured-json-nim"


@pytest.mark.asyncio
async def test_overloaded_and_model_not_found_causes():
    async def run(status: int, body: dict, expected: LLMCause):
        clear_model_cooldowns()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(LLMGatewayError) as ei:
                await chat_completion(
                    client,
                    model="structured-json-gemini",
                    messages=[{"role": "user", "content": "hi"}],
                    max_attempts=1,
                )
            assert ei.value.cause == expected

    await run(503, {"error": {"code": "overloaded"}}, LLMCause.overloaded)
    await run(404, {"error": {"code": "model_not_found"}}, LLMCause.model_not_found)
    await run(401, {"error": {"code": "invalid_api_key"}}, LLMCause.auth_failed)
