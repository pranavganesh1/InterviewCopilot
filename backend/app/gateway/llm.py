import asyncio
import hashlib
import time
from contextvars import ContextVar
from datetime import UTC, datetime

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


class LLMGatewayError(Exception):
    """Raised when the LLM gateway call fails after retries."""


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
    max_attempts: int = 3,
) -> str:
    """Call the LiteLLM proxy (OpenAI-compatible) and return the assistant content.

    Every successful call is logged to Mongo llm_call_logs (metadata only,
    never full prompts, per spec §7).
    """
    chain = [model, *MODEL_FALLBACKS.get(model, [])]
    last_error: Exception | None = None
    for idx, candidate in enumerate(chain):
        # Primary gets the full timeout; fallbacks a tight one (a hanging
        # provider must not stall past the caller's patience).
        timeout_s = (
            get_settings().llm_client_timeout
            if idx == 0
            else min(get_settings().llm_client_timeout, 30)
        )
        try:
            content = await _chat_once(
                client,
                timeout_s=timeout_s,
                model=candidate,
                messages=messages,
                mongo_db=mongo_db,
                request_id=request_id,
                temperature=temperature,
                response_format=response_format,
                meta=meta,
                max_attempts=max_attempts,
            )
        except LLMGatewayError as exc:
            last_error = exc
            log.warning("llm_model_failed", model=candidate, error=str(exc)[:200])
            continue
        llm_model_used.set(candidate)
        return content
    raise last_error or LLMGatewayError("LLM gateway call failed")


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
) -> str:
    settings = get_settings()
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if response_format is not None:
        payload["response_format"] = response_format

    started = time.monotonic()
    # 429 strategy: one quick 5s retry on the same model (covers per-minute
    # bursts), then the caller's fallback chain takes over immediately —
    # waiting 90s+ on an exhausted DAILY quota helps nobody (M11 finding).
    last_error: Exception | None = None
    data: dict | None = None
    for attempt in range(max_attempts):
        try:
            resp = await client.post(
                f"{settings.litellm_url}/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                timeout=timeout_s,
            )
            if resp.status_code == 429 and attempt < max_attempts - 1:
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if retry_after else 5
                log.warning(
                    "llm_gateway_rate_limited",
                    model=model,
                    attempt=attempt + 1,
                    backoff_s=delay,
                )
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except (httpx.HTTPError, KeyError) as exc:
            last_error = exc
            break
    if data is None:
        log.error("llm_gateway_failed", model=model, error=str(last_error))
        raise LLMGatewayError(f"LLM gateway call failed: {last_error}") from last_error
    latency_ms = int((time.monotonic() - started) * 1000)

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
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
