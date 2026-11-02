from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import conversation_store, onboarding_service
from app.services.vault_service import list_items

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await onboarding_service.chat(
        db,
        request.app.state.mongo_db,
        user,
        body.message,
        request_id=request.headers.get("x-request-id"),
    )


@router.get("/state")
async def state(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    messages = await conversation_store.get_messages(
        request.app.state.mongo_db, str(user.id), limit=100
    )
    items = await list_items(db, user.id)
    return {
        "messages": messages,
        "vault_items": [
            {"id": str(i.id), "category": i.category, "title": i.title, "source": i.source}
            for i in items
        ],
    }
