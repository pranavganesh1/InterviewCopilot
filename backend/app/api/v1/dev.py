import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.gateway.llm import chat_completion

router = APIRouter(prefix="/dev", tags=["dev"])


class LLMCheckRequest(BaseModel):
    prompt: str


@router.post("/llm-check")
async def llm_check(body: LLMCheckRequest, request: Request):
    if get_settings().app_env != "local":
        raise HTTPException(status_code=404, detail="Not found")
    async with httpx.AsyncClient(timeout=70) as client:
        content = await chat_completion(
            client,
            model="interview-chat",
            messages=[{"role": "user", "content": body.prompt}],
            mongo_db=request.app.state.mongo_db,
            request_id=request.headers.get("x-request-id"),
        )
    return {"content": content}
