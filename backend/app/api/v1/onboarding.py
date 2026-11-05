from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import conversation_store, onboarding_service
from app.services.vault_service import list_items

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_REQUIRED = ("project", "skill", "education")


class ChatRequest(BaseModel):
    message: str = Field(max_length=20000)


def _vault_status(items) -> tuple[bool, list[str]]:
    categories = {i.category for i in items}
    missing = [c for c in _REQUIRED if c not in categories]
    return len(missing) == 0, missing


async def _state_payload(mongo_db, db: AsyncSession, user: User) -> dict:
    messages = await conversation_store.get_messages(mongo_db, str(user.id), limit=100)
    items = await list_items(db, user.id)
    vault_ready, missing = _vault_status(items)
    finished = user.onboarding_completed_at is not None
    return {
        "messages": messages,
        "vault_items": [
            {"id": str(i.id), "category": i.category, "title": i.title, "source": i.source}
            for i in items
        ],
        # Vault criteria (coach / readiness).
        "onboarding_complete": vault_ready or finished,
        "missing_categories": [] if finished else missing,
        # Explicit user finish — survives refresh/login.
        "onboarding_finished": finished,
        "onboarding_completed_at": (
            user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None
        ),
    }


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
        already_finished=user.onboarding_completed_at is not None,
    )


@router.get("/state")
async def state(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _state_payload(request.app.state.mongo_db, db, user)


@router.post("/complete")
async def complete(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark onboarding finished and return refreshed state (idempotent).

    Messages and vault items are already persisted by chat/resume uploads.
    This records the user's explicit Finish action so Tracks stays the home
    experience after refresh or re-login.
    """
    items = await list_items(db, user.id)
    vault_ready, missing = _vault_status(items)
    if not vault_ready and user.onboarding_completed_at is None:
        raise HTTPException(
            status_code=409,
            detail=("Onboarding is not ready yet. Still needed: " + ", ".join(missing)),
        )
    if user.onboarding_completed_at is None:
        user.onboarding_completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(user)
    return await _state_payload(request.app.state.mongo_db, db, user)
