import hashlib
import time
from datetime import UTC, datetime

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


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
) -> str:
    """Call the LiteLLM proxy (OpenAI-compatible) and return the assistant content.

    Every successful call is logged to Mongo llm_call_logs (metadata only,
    never full prompts, per spec §7).
    """
    settings = get_settings()
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if response_format is not None:
        payload["response_format"] = response_format

    started = time.monotonic()
    try:
        resp = await client.post(
            f"{settings.litellm_url}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, KeyError) as exc:
        log.error("llm_gateway_failed", model=model, error=str(exc))
        raise LLMGatewayError(f"LLM gateway call failed: {exc}") from exc
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
                "created_at": datetime.now(UTC),
            }
        )
    return content
