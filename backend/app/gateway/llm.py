import asyncio
import hashlib
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import StrEnum

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.logging import get_logger
from app.gateway.pricing import estimate_cost_usd

log = get_logger(__name__)

# Mirrors infra/litellm/config.yaml so a failed primary is visible to tests
# and the model that actually answered can be stored on the evaluation.
MODEL_FALLBACKS: dict[str, list[str]] = {
    "interview-chat": ["interview-chat-nim", "interview-chat-gemini"],
    "structured-json": ["structured-json-nim", "structured-json-gemini"],
}

# Set on each successful chat_completion. Interview turns copy this onto
# evaluation_detail so reports can say which model scored the answer.
llm_model_used: ContextVar[str | None] = ContextVar("llm_model_used", default=None)

# Skip a deployment briefly after rate_limited / overloaded / timeout.
_COOLDOWN_S = 45.0
_model_cooldown_until: dict[str, float] = {}


class LLMCause(StrEnum):
    rate_limited = "rate_limited"
    overloaded = "overloaded"
    model_not_found = "model_not_found"
    auth_failed = "auth_failed"
    schema_rejected = "schema_rejected"
    timeout = "timeout"
    network = "network"
    unknown = "unknown"


class LLMGatewayError(Exception):
    """Raised when the LLM gateway call fails after retries."""

    def __init__(
        self,
        message: str,
        *,
        cause: LLMCause = LLMCause.unknown,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        model: str | None = None,
        provider_code: str | None = None,
    ):
        super().__init__(message)
        self.cause = cause
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.model = model
        self.provider_code = provider_code


def _cooldown_active(model: str) -> bool:
    until = _model_cooldown_until.get(model, 0.0)
    return time.monotonic() < until


def _set_cooldown(model: str, seconds: float | None = None) -> None:
    _model_cooldown_until[model] = time.monotonic() + (seconds or _COOLDOWN_S)


def clear_model_cooldowns() -> None:
    """Test helper — wipe deployment cooldowns."""
    _model_cooldown_until.clear()


def _provider_code_from_body(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if isinstance(err, dict):
        for key in ("code", "type", "status", "message"):
            val = err.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:120]
        return None
    if isinstance(err, str) and err.strip():
        return err.strip()[:120]
    for key in ("code", "type", "status"):
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:120]
    return None


def classify_http_failure(
    status_code: int | None,
    *,
    provider_code: str | None = None,
    exc: BaseException | None = None,
) -> LLMCause:
    code = (provider_code or "").upper()
    text = f"{provider_code or ''} {exc or ''}".lower()
    if status_code == 429 or "RESOURCE_EXHAUSTED" in code or "rate" in text:
        return LLMCause.rate_limited
    if status_code in (503, 529) or "overloaded" in text or "unavailable" in text:
        return LLMCause.overloaded
    if status_code == 404 or "model_not_found" in text or "not_found" in code.lower():
        return LLMCause.model_not_found
    if status_code in (401, 403) or "invalid_api_key" in text or "auth" in text:
        return LLMCause.auth_failed
    if (
        status_code == 400
        and any(k in text for k in ("schema", "additionalproperties", "$ref", "json_schema"))
    ) or "schema" in code.lower():
        return LLMCause.schema_rejected
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)) or "timeout" in text:
        return LLMCause.timeout
    if isinstance(exc, (httpx.NetworkError, httpx.ConnectError)) or "connect" in text:
        return LLMCause.network
    return LLMCause.unknown


def _parse_retry_after(resp: httpx.Response | None) -> float | None:
    if resp is None:
        return None
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def chat_completion(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict],
    mongo_db: AsyncIOMotorDatabase | None = None,
    request_id: str | None = None,
    temperature: float | None = None,
    response_format: dict | None = None,
    meta: dict | None = None,
    max_attempts: int = 2,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
) -> str:
    """Call the LiteLLM proxy (OpenAI-compatible) and return the assistant content.

    Every successful call is logged to Mongo llm_call_logs (metadata only,
    never full prompts, per spec §7).
    """
    chain = [model, *MODEL_FALLBACKS.get(model, [])]
    last_error: LLMGatewayError | None = None
    chain_started = time.monotonic()
    total_budget = (
        timeout_s
        if timeout_s is not None
        else min(float(get_settings().llm_client_timeout), 28.0)
    )

    for idx, candidate in enumerate(chain):
        remaining = total_budget - (time.monotonic() - chain_started)
        if remaining < 2.0:
            break
        if _cooldown_active(candidate):
            log.info(
                "llm_model_cooldown_skip",
                model=candidate,
                cause=LLMCause.rate_limited.value,
            )
            continue
        # Primary uses remaining budget; fallbacks stay tighter.
        candidate_timeout = min(remaining, 15.0 if idx == 0 else 12.0)
        try:
            content = await _chat_once(
                client,
                timeout_s=candidate_timeout,
                model=candidate,
                messages=messages,
                mongo_db=mongo_db,
                request_id=request_id,
                temperature=temperature,
                response_format=response_format,
                meta=meta,
                max_attempts=max_attempts,
                max_tokens=max_tokens,
            )
        except LLMGatewayError as exc:
            last_error = exc
            if exc.cause in (
                LLMCause.rate_limited,
                LLMCause.overloaded,
                LLMCause.timeout,
            ):
                _set_cooldown(
                    candidate,
                    max(exc.retry_after_seconds or _COOLDOWN_S, 30.0),
                )
            log.warning(
                "llm_model_failed",
                model=candidate,
                cause=exc.cause.value,
                status_code=exc.status_code,
                provider_code=exc.provider_code,
                retry_after_seconds=exc.retry_after_seconds,
                attempt=idx + 1,
                elapsed_ms=int((time.monotonic() - chain_started) * 1000),
                error=str(exc)[:200],
            )
            # Auth / not-found on a deployment: try next; don't burn retries.
            continue
        llm_model_used.set(candidate)
        log.info(
            "llm_chat_ok",
            model=candidate,
            fallback_index=idx,
            elapsed_ms=int((time.monotonic() - chain_started) * 1000),
        )
        return content
    raise last_error or LLMGatewayError(
        "LLM gateway call failed", cause=LLMCause.unknown
    )


async def _chat_once(
    client: httpx.AsyncClient,
    *,
    timeout_s: float,
    model: str,
    messages: list[dict],
    mongo_db: AsyncIOMotorDatabase | None,
    request_id: str | None,
    temperature: float | None,
    response_format: dict | None,
    meta: dict | None,
    max_attempts: int,
    max_tokens: int | None = None,
) -> str:
    settings = get_settings()
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if response_format is not None:
        payload["response_format"] = response_format
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    started = time.monotonic()
    last_error: LLMGatewayError | None = None
    data: dict | None = None
    attempts = max(1, min(max_attempts, 2))

    for attempt in range(attempts):
        try:
            resp = await client.post(
                f"{settings.litellm_url}/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                timeout=timeout_s,
            )
        except httpx.TimeoutException:
            cause = LLMCause.timeout
            last_error = LLMGatewayError(
                f"timeout: {model}",
                cause=cause,
                model=model,
            )
            log.warning(
                "llm_gateway_http_error",
                model=model,
                cause=cause.value,
                status_code=None,
                provider_code=None,
                retry_after_seconds=None,
                attempt=attempt + 1,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            break
        except httpx.HTTPError as exc:
            cause = classify_http_failure(None, exc=exc)
            last_error = LLMGatewayError(
                f"network: {type(exc).__name__}",
                cause=cause,
                model=model,
            )
            log.warning(
                "llm_gateway_http_error",
                model=model,
                cause=cause.value,
                status_code=None,
                provider_code=None,
                retry_after_seconds=None,
                attempt=attempt + 1,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            break

        body: object = None
        try:
            body = resp.json()
        except Exception:
            body = None
        provider_code = _provider_code_from_body(body)
        retry_after = _parse_retry_after(resp)

        if resp.status_code == 429:
            cause = classify_http_failure(429, provider_code=provider_code)
            delay = min(retry_after if retry_after is not None else 1.5, 2.0)
            log.warning(
                "llm_gateway_http_error",
                model=model,
                cause=cause.value,
                status_code=429,
                provider_code=provider_code,
                retry_after_seconds=retry_after or delay,
                attempt=attempt + 1,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            if attempt < attempts - 1:
                await asyncio.sleep(delay)
                continue
            raise LLMGatewayError(
                f"rate limited: {model}",
                cause=cause,
                status_code=429,
                retry_after_seconds=retry_after or 30.0,
                model=model,
                provider_code=provider_code,
            )

        if resp.status_code >= 400:
            cause = classify_http_failure(
                resp.status_code, provider_code=provider_code
            )
            log.warning(
                "llm_gateway_http_error",
                model=model,
                cause=cause.value,
                status_code=resp.status_code,
                provider_code=provider_code,
                retry_after_seconds=retry_after,
                attempt=attempt + 1,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            raise LLMGatewayError(
                f"HTTP {resp.status_code}: {model}",
                cause=cause,
                status_code=resp.status_code,
                retry_after_seconds=retry_after,
                model=model,
                provider_code=provider_code,
            )

        if not isinstance(body, dict):
            last_error = LLMGatewayError(
                f"invalid response: {model}",
                cause=LLMCause.unknown,
                status_code=resp.status_code,
                model=model,
            )
            break
        data = body
        break

    if data is None:
        err = last_error or LLMGatewayError(
            "LLM gateway call failed", cause=LLMCause.unknown, model=model
        )
        log.error(
            "llm_gateway_failed",
            model=model,
            cause=err.cause.value,
            status_code=err.status_code,
            provider_code=err.provider_code,
        )
        raise err

    latency_ms = int((time.monotonic() - started) * 1000)
    log.info("llm_call_timing", model=model, latency_ms=latency_ms)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMGatewayError(
            f"malformed completion: {model}",
            cause=LLMCause.unknown,
            model=model,
        ) from exc
    usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
    if mongo_db is not None:
        await mongo_db.llm_call_logs.insert_one(
            {
                "request_id": request_id,
                "model": model,
                "latency_ms": latency_ms,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "prompt_sha256": hashlib.sha256(repr(messages).encode()).hexdigest(),
                "status": "ok",
                "estimated_cost_usd": estimate_cost_usd(
                    model,
                    usage.get("prompt_tokens") or 0,
                    usage.get("completion_tokens") or 0,
                ),
                **(meta or {}),
                "created_at": datetime.now(UTC),
            }
        )
    return content
