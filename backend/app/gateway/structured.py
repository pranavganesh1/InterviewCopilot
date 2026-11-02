import json

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ValidationError

from app.gateway.llm import LLMGatewayError, chat_completion


async def structured_completion(
    client: httpx.AsyncClient,
    *,
    system: str,
    user_payload: dict,
    schema: type[BaseModel],
    model: str = "structured-json",
    mongo_db: AsyncIOMotorDatabase | None = None,
    request_id: str | None = None,
) -> BaseModel:
    """Ask for JSON, validate against schema, repair once, then give up.

    Agents use this for every structured decision (extraction, question
    planning, evidence scoring). Raises LLMGatewayError if the model cannot
    produce schema-valid JSON within two attempts.
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
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
    for _ in range(2):
        raw = await chat_completion(
            client,
            model=model,
            messages=messages,
            mongo_db=mongo_db,
            request_id=request_id,
            response_format={"type": "json_object"},
        )
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
    raise LLMGatewayError(f"structured output invalid after repair retry: {last_error}")
