import copy
import json

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ValidationError

from app.gateway.llm import LLMCause, LLMGatewayError, chat_completion


def gemini_safe_schema(schema: dict) -> dict:
    """Flatten a JSON schema for Gemini: drop unsupported keywords/$defs."""
    unsupported = {
        "additionalProperties",
        "$defs",
        "definitions",
        "$schema",
        "default",
        "title",
        "examples",
        "const",
    }

    def _walk(node: object) -> object:
        if isinstance(node, list):
            return [_walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        out: dict = {}
        for key, val in node.items():
            if key in unsupported:
                continue
            if key == "$ref":
                # Inline refs are unresolved after dropping $defs — skip.
                continue
            out[key] = _walk(val)
        # Gemini prefers explicit object typing.
        if out.get("type") == "object" and "properties" in out:
            out.setdefault("required", list(out["properties"].keys()))
        return out

    return _walk(copy.deepcopy(schema))  # type: ignore[return-value]


async def structured_completion(
    client: httpx.AsyncClient,
    *,
    system: str,
    user_payload: dict,
    schema: type[BaseModel],
    model: str = "structured-json",
    mongo_db: AsyncIOMotorDatabase | None = None,
    request_id: str | None = None,
    temperature: float | None = None,
    meta: dict | None = None,
    max_attempts: int = 2,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
    repair_attempts: int = 2,
) -> BaseModel:
    """Ask for JSON, validate against schema, repair once, then give up.

    Agents use this for every structured decision (extraction, question
    planning, evidence scoring). Raises LLMGatewayError if the model cannot
    produce schema-valid JSON within two attempts. max_attempts is forwarded
    to chat_completion (per-model 429 attempts) — callers with a cheap
    deterministic fallback (question planning) pass 1 to fail fast.
    """
    raw_schema = schema.model_json_schema()
    safe_schema = gemini_safe_schema(raw_schema)
    schema_json = json.dumps(safe_schema, indent=2)
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                f"{system}\n\nRespond with ONLY valid JSON matching this JSON schema:\n"
                f"{schema_json}"
            ),
        },
        {"role": "user", "content": json.dumps(user_payload)},
    ]
    last_error: Exception | None = None
    used_plain_json = False

    for _attempt in range(max(1, repair_attempts)):
        response_format: dict | None = {"type": "json_object"}
        # After a schema rejection from the provider, fall back to plain JSON mode.
        if used_plain_json:
            response_format = None
        try:
            raw = await chat_completion(
                client,
                model=model,
                messages=messages,
                mongo_db=mongo_db,
                request_id=request_id,
                temperature=temperature,
                response_format=response_format,
                meta=meta,
                max_attempts=max_attempts,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
            )
        except LLMGatewayError as exc:
            if exc.cause == LLMCause.schema_rejected and not used_plain_json:
                used_plain_json = True
                last_error = exc
                continue
            raise
        try:
            data = json.loads(raw)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous output was invalid: {exc}. "
                        "Respond with ONLY corrected JSON matching the required schema."
                    ),
                }
            )
    raise LLMGatewayError(
        f"structured output invalid after repair retry: {last_error}",
        cause=LLMCause.schema_rejected,
    )
