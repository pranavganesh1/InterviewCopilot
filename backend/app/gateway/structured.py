import copy
import json
import re

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ValidationError

from app.gateway.llm import LLMCause, LLMGatewayError, chat_completion, get_http_client

_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$", re.IGNORECASE
)


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


def parse_json_content(raw: str) -> object:
    """Parse model JSON; tolerate markdown fences and leading/trailing noise."""
    text = (raw or "").strip()
    if not text:
        raise json.JSONDecodeError("empty", raw or "", 0)
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Extract first {...} or [...] object if the model added prose.
        start_obj = text.find("{")
        start_arr = text.find("[")
        if start_obj < 0 and start_arr < 0:
            raise
        if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
            start, end_char = start_arr, "]"
        else:
            start, end_char = start_obj, "}"
        end = text.rfind(end_char)
        if end <= start:
            raise
        return json.loads(text[start : end + 1])


async def structured_completion(
    client: httpx.AsyncClient | None = None,
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

    Agents use this for every structured decision. Raises LLMGatewayError if
    the model cannot produce schema-valid JSON. Repair calls use max_attempts=1
    so a formatting miss does not fan out across the full fallback chain twice.
    """
    http = client or await get_http_client()
    raw_schema = schema.model_json_schema()
    safe_schema = gemini_safe_schema(raw_schema)
    # Compact schema JSON — indent=2 was wasting hundreds of prompt tokens/turn.
    schema_json = json.dumps(safe_schema, separators=(",", ":"))
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                f"{system}\n\nRespond with ONLY valid JSON matching this JSON schema:\n"
                f"{schema_json}"
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, separators=(",", ":"))},
    ]
    last_error: Exception | None = None
    used_plain_json = False
    repairs = max(1, min(int(repair_attempts), 2))

    for attempt in range(repairs):
        response_format: dict | None = {"type": "json_object"}
        # After a schema rejection from the provider, fall back to plain JSON mode.
        if used_plain_json:
            response_format = None
        # First try may use caller's max_attempts; repair tries once on primary chain.
        attempt_budget = max_attempts if attempt == 0 else 1
        try:
            raw = await chat_completion(
                http,
                model=model,
                messages=messages,
                mongo_db=mongo_db,
                request_id=request_id,
                temperature=temperature,
                response_format=response_format,
                meta=meta,
                max_attempts=attempt_budget,
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
            data = parse_json_content(raw)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            last_error = exc
            if attempt >= repairs - 1:
                break
            # Keep repair prompts short — do not re-send huge invalid blobs.
            snippet = (raw or "")[:400]
            messages.append({"role": "assistant", "content": snippet})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous output was invalid ({type(exc).__name__}). "
                        "Respond with ONLY corrected JSON matching the required schema. "
                        "No markdown fences."
                    ),
                }
            )
    err_name = type(last_error).__name__ if last_error else "unknown"
    raise LLMGatewayError(
        f"structured output invalid after repair retry: {err_name}",
        cause=LLMCause.schema_rejected,
        retry_after_seconds=8.0,
    )
