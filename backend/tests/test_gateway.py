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
    gateway_error_detail,
)
from app.gateway.structured import gemini_safe_schema, parse_json_content


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
async def test_explicit_timeout_gives_primary_longer_than_default_cap(monkeypatch):
    """Resume/feedback pass timeout_s — primary must not be hard-capped at 9s."""
    seen_timeouts: list[float] = []

    async def fake_once(client, *, timeout_s, model, **kwargs):
        seen_timeouts.append(timeout_s)
        if model == "structured-json":
            raise LLMGatewayError("timeout: structured-json", cause=LLMCause.timeout, model=model)
        return '{"ok": true}'

    monkeypatch.setattr("app.gateway.llm._chat_once", fake_once)
    async with httpx.AsyncClient() as client:
        content = await chat_completion(
            client,
            model="structured-json",
            messages=[{"role": "user", "content": "hi"}],
            max_attempts=1,
            timeout_s=60.0,
        )
    assert content == '{"ok": true}'
    assert seen_timeouts[0] >= 40.0  # primary share of 60s, not the 9s interview cap


@pytest.mark.asyncio
async def test_schema_rejected_does_not_burn_fallbacks():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["model"])
        return httpx.Response(
            400,
            json={"error": {"code": "json_validate_failed", "message": "Failed to validate JSON"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMGatewayError) as ei:
            await chat_completion(
                client,
                model="structured-json",
                messages=[{"role": "user", "content": "hi"}],
                max_attempts=1,
            )
    assert ei.value.cause == LLMCause.schema_rejected
    assert seen == ["structured-json"]


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
    assert seen == ["structured-json", "structured-json-gemini"]
    assert llm_model_used.get() == "structured-json-gemini"


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
    assert seen[1] == "structured-json-gemini"


@pytest.mark.asyncio
async def test_second_rate_limit_stops_before_third_provider():
    """One customer request must not fan out to every fallback after 429s."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["model"])
        return httpx.Response(
            429,
            headers={"Retry-After": "15"},
            json={"error": {"code": "RESOURCE_EXHAUSTED"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMGatewayError) as ei:
            await chat_completion(
                client,
                model="structured-json",
                messages=[{"role": "user", "content": "hi"}],
                max_attempts=1,
            )
    assert ei.value.cause == LLMCause.rate_limited
    assert ei.value.retry_after_seconds == 15.0
    # Primary + one Gemini fallback; second 429 stops the chain (no NIM).
    assert seen == ["structured-json", "structured-json-gemini"]
    assert "structured-json-nim" not in seen


def test_gateway_error_detail_is_customer_safe():
    detail = gateway_error_detail(
        LLMGatewayError("x", cause=LLMCause.rate_limited, retry_after_seconds=12)
    )
    assert detail["cause"] == "rate_limited"
    assert detail["retry_after_seconds"] == 12
    assert "Temporary request limit" in detail["message"]
    assert "litellm" not in detail["message"].lower()
    schema = gateway_error_detail(LLMGatewayError("x", cause=LLMCause.schema_rejected))
    assert schema["cause"] == "schema_rejected"
    assert "invalid" in schema["message"].lower()


def test_groq_json_validate_classified_as_schema_rejected():
    from app.gateway.llm import classify_http_failure

    cause = classify_http_failure(
        400, provider_code="json_validate_failed", exc=None
    )
    assert cause == LLMCause.schema_rejected
    cause2 = classify_http_failure(
        400, provider_code="invalid_request_error", exc=Exception("Failed to validate JSON")
    )
    assert cause2 == LLMCause.schema_rejected


@pytest.mark.asyncio
async def test_reasoning_field_used_when_content_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning": '{"ok": true}',
                        }
                    }
                ],
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
    assert content == '{"ok": true}'


def test_parse_json_content_tolerates_fences_and_prose():
    assert parse_json_content('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_content('Here you go:\n{"a": 2}\nThanks') == {"a": 2}


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
    assert seen[0] == "structured-json-gemini"


@pytest.mark.asyncio
async def test_skips_gemini_on_overload_cooldown_after_primary_timeout(monkeypatch):
    """Primary timeout must not re-hit Gemini while it is already overload-cooling."""
    from app.gateway import llm as llm_mod

    llm_mod._set_cooldown(
        "structured-json-gemini", 20.0, cause=LLMCause.overloaded.value
    )
    seen: list[str] = []

    async def fake_once(client, *, timeout_s, model, **kwargs):
        seen.append(model)
        raise LLMGatewayError("timeout", cause=LLMCause.timeout, model=model)

    monkeypatch.setattr(llm_mod, "_chat_once", fake_once)
    with pytest.raises(LLMGatewayError) as ei:
        await chat_completion(
            None,
            model="structured-json",
            messages=[{"role": "user", "content": "hi"}],
            max_attempts=1,
        )
    assert seen == ["structured-json"]
    assert ei.value.cause == LLMCause.timeout


@pytest.mark.asyncio
async def test_skips_gemini_on_overload_cooldown_after_primary_429(monkeypatch):
    from app.gateway import llm as llm_mod

    llm_mod._set_cooldown(
        "structured-json-gemini", 20.0, cause=LLMCause.overloaded.value
    )
    seen: list[str] = []

    async def fake_once(client, *, timeout_s, model, **kwargs):
        seen.append(model)
        raise LLMGatewayError(
            "rl",
            cause=LLMCause.rate_limited,
            status_code=429,
            retry_after_seconds=30.0,
            model=model,
        )

    monkeypatch.setattr(llm_mod, "_chat_once", fake_once)
    with pytest.raises(LLMGatewayError) as ei:
        await chat_completion(
            None,
            model="structured-json",
            messages=[{"role": "user", "content": "hi"}],
            max_attempts=1,
        )
    assert seen == ["structured-json"]
    assert ei.value.cause == LLMCause.rate_limited
    assert ei.value.retry_after_seconds == 30.0


@pytest.mark.asyncio
async def test_entire_chain_cooling_fails_fast_without_bypass(monkeypatch):
    """Do not bypass cooldowns when every deployment is cooling — that hammered Gemini."""
    from app.gateway import llm as llm_mod

    llm_mod._set_cooldown(
        "structured-json", 25.0, cause=LLMCause.rate_limited.value
    )
    llm_mod._set_cooldown(
        "structured-json-gemini", 25.0, cause=LLMCause.overloaded.value
    )
    seen: list[str] = []

    async def fake_once(client, *, timeout_s, model, **kwargs):
        seen.append(model)
        return "should-not-run"

    monkeypatch.setattr(llm_mod, "_chat_once", fake_once)
    with pytest.raises(LLMGatewayError) as ei:
        await chat_completion(
            None,
            model="structured-json",
            messages=[{"role": "user", "content": "hi"}],
            max_attempts=1,
        )
    assert seen == []
    assert ei.value.cause == LLMCause.rate_limited
    assert 8.0 <= (ei.value.retry_after_seconds or 0) <= 45.0
    detail = gateway_error_detail(ei.value)
    assert detail["cause"] == "rate_limited"
    assert detail["retry_after_seconds"] >= 8


@pytest.mark.asyncio
async def test_second_request_does_not_bypass_gemini_after_overload():
    """After Groq 429 + Gemini 503, next request must not re-call cooling Gemini."""
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
        return httpx.Response(503, json={"error": {"code": "overloaded"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMGatewayError) as first:
            await chat_completion(
                client,
                model="structured-json",
                messages=[{"role": "user", "content": "hi"}],
                max_attempts=1,
            )
        assert first.value.cause == LLMCause.rate_limited
        assert seen == ["structured-json", "structured-json-gemini"]
        seen.clear()
        with pytest.raises(LLMGatewayError) as second:
            await chat_completion(
                client,
                model="structured-json",
                messages=[{"role": "user", "content": "again"}],
                max_attempts=1,
            )
    # Both deployments cooling — no provider calls, no cooldown bypass.
    assert seen == []
    assert second.value.cause == LLMCause.rate_limited
    assert (second.value.retry_after_seconds or 0) >= 8


def test_gateway_error_detail_overloaded_defaults_retry_after_20():
    detail = gateway_error_detail(LLMGatewayError("x", cause=LLMCause.overloaded))
    assert detail["cause"] == "overloaded"
    assert detail["retry_after_seconds"] == 20
    assert "Temporary service overload" in detail["message"]


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
