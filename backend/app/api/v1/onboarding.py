from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.sqlalchemy import get_db
from app.gateway.llm import LLMGatewayError, gateway_error_detail
from app.models.user import User
from app.services import conversation_store, onboarding_service
from app.services.preparation_goals import preferences_ready
from app.services.vault_service import list_items

log = get_logger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Suggested vault sections — informational only; never block Start Preparing.
_SUGGESTED = ("project", "skill", "education")


class ChatRequest(BaseModel):
    message: str = Field(max_length=20000)
    # Client-generated id for idempotent retries (additive; optional).
    message_id: str | None = Field(default=None, max_length=80)


class GoalsRequest(BaseModel):
    interests: list[str] = Field(default_factory=list)
    target_role: str | None = None
    technical_areas: list[str] | None = None
    focus_skills: list[str] | None = None
    focus_projects: list[str] | None = None
    project_aspects: list[str] | None = None
    placement_target: str | None = None
    experience_level: str | None = None
    behavioral_goals: str | None = None
    confirmed: bool | None = None


class StarterRequest(BaseModel):
    starter_id: str = Field(max_length=64)


class ReviewItemStatus(BaseModel):
    item_id: str
    status: str
    reason: str | None = None


class ReviewPatchRequest(BaseModel):
    summary: str | None = Field(default=None, max_length=8000)
    item_statuses: list[ReviewItemStatus] | None = None
    selected_next_track_id: str | None = None


class StartRecommendedRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=255)
    track_type: str | None = Field(default=None, max_length=32)


def _vault_status(items) -> tuple[bool, list[str]]:
    """Return (ready_for_goals, optional_missing). Ready if any vault signal exists."""
    categories = {i.category for i in items}
    missing = [c for c in _SUGGESTED if c not in categories]
    # Any extracted item unlocks goals; empty vault still OK via proceed_to_goals.
    return True, missing


async def _state_payload(mongo_db, db: AsyncSession, user: User) -> dict:
    await onboarding_service.ensure_review_opener(db, mongo_db, user)
    await onboarding_service.ensure_goals_intro(db, mongo_db, user)
    messages = await conversation_store.get_messages(mongo_db, str(user.id), limit=100)
    items = await list_items(db, user.id)
    vault_ready, missing = _vault_status(items)
    finished = user.onboarding_completed_at is not None
    extras = await onboarding_service.state_extras(db, mongo_db, user)
    return {
        "messages": messages,
        "vault_items": [
            {
                "id": str(i.id),
                "category": i.category,
                "title": i.title,
                "details": i.details or {},
                "source": i.source,
            }
            for i in items
        ],
        # Preferences (or finished) mark onboarding complete — vault sections are optional.
        "onboarding_complete": finished
        or preferences_ready(extras.get("preparation_preferences")),
        "missing_categories": [] if finished else missing,
        "optional_categories": True,
        "vault_ready": vault_ready,
        # Explicit user finish — survives refresh/login.
        "onboarding_finished": finished,
        "onboarding_completed_at": (
            user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None
        ),
        **extras,
    }


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await onboarding_service.ensure_review_opener(db, request.app.state.mongo_db, user)
    await onboarding_service.ensure_goals_intro(db, request.app.state.mongo_db, user)
    try:
        return await onboarding_service.chat(
            db,
            request.app.state.mongo_db,
            user,
            body.message,
            request_id=request.headers.get("x-request-id"),
            already_finished=user.onboarding_completed_at is not None,
            message_id=body.message_id,
        )
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail=gateway_error_detail(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        name = type(exc).__name__
        # SQLAlchemy / driver / Mongo-ish names → persistence; else internal.
        persistence = any(
            k in name.lower()
            for k in (
                "sqlalchemy",
                "operational",
                "integrity",
                "dbapi",
                "mongo",
                "pymongo",
                "timeout",
            )
        ) or any(
            k in str(exc).lower()[:120]
            for k in ("connection refused", "server closed", "duplicate key")
        )
        log.warning(
            "onboarding_chat_unhandled",
            cause="persistence" if persistence else "internal",
            exc_type=name,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Could not save your reply. Please try again."
                    if persistence
                    else "Something went wrong on our side. Please try again."
                ),
                "cause": "persistence" if persistence else "unknown",
                "retry_after_seconds": 15,
            },
        ) from exc


@router.post("/starter")
async def conversation_starter(
    body: StarterRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kick off a focused onboarding conversation from a starter card."""
    await onboarding_service.ensure_review_opener(db, request.app.state.mongo_db, user)
    try:
        return await onboarding_service.start_conversation_starter(
            db,
            request.app.state.mongo_db,
            user,
            body.starter_id,
            already_finished=user.onboarding_completed_at is not None,
            request_id=request.headers.get("x-request-id"),
        )
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail=gateway_error_detail(exc),
        ) from exc


@router.get("/state")
async def state(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _state_payload(request.app.state.mongo_db, db, user)


@router.post("/goals")
async def save_goals(
    body: GoalsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save interactive goal selections and return the next coach follow-up."""
    return await onboarding_service.save_goals(
        db,
        request.app.state.mongo_db,
        user,
        body.model_dump(exclude_none=True),
        already_finished=user.onboarding_completed_at is not None,
        request_id=request.headers.get("x-request-id"),
    )


@router.post("/goals/confirm")
async def confirm_goals(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await onboarding_service.confirm_goals(request.app.state.mongo_db, user)
    return await _state_payload(request.app.state.mongo_db, db, user)


@router.post("/complete")
async def complete(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark onboarding finished and return refreshed state (idempotent).

    Requires preparation goals (vault sections are optional).
    """
    prefs = await conversation_store.get_preparation_preferences(
        request.app.state.mongo_db, str(user.id)
    )
    if user.onboarding_completed_at is None and not preferences_ready(prefs):
        if not prefs.get("interests"):
            raise HTTPException(
                status_code=409,
                detail="Choose your interview preparation goals before starting.",
            )
        # Interests chosen but not confirmed — confirm now as part of Start Preparing.
        await onboarding_service.confirm_goals(request.app.state.mongo_db, user)
    first_finish = user.onboarding_completed_at is None
    if first_finish:
        user.onboarding_completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(user)
    # Personalized post-onboarding review + roadmap (idempotent refresh).
    await onboarding_service.ensure_profile_review(
        db, request.app.state.mongo_db, user, force=first_finish
    )
    payload = await _state_payload(request.app.state.mongo_db, db, user)
    # Offer the start-interview popup once on first finish (additive field).
    if first_finish and not await conversation_store.get_start_offer_shown(
        request.app.state.mongo_db, str(user.id)
    ):
        seeds = payload.get("recommended_tracks") or []
        seed = seeds[0] if seeds else {}
        subject = (
            (seed.get("subject") if isinstance(seed, dict) else None)
            or (prefs.get("target_role") if isinstance(prefs, dict) else None)
            or "your focus area"
        )
        payload["offer_start_interview"] = {
            "subject": str(subject),
            "track_type": (
                seed.get("track_type") if isinstance(seed, dict) else None
            )
            or "topic",
            "reason": "onboarding_finished",
        }
        await conversation_store.mark_start_offer_shown(
            request.app.state.mongo_db, str(user.id)
        )
    return payload


@router.get("/review")
async def get_review(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await onboarding_service.get_profile_review_payload(
        db, request.app.state.mongo_db, user, ensure=True
    )


@router.patch("/review")
async def patch_review(
    body: ReviewPatchRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patch = body.model_dump(exclude_none=True)
    if "item_statuses" in patch:
        patch["item_statuses"] = [s.model_dump() for s in body.item_statuses or []]
    return await onboarding_service.patch_profile_review(
        db, request.app.state.mongo_db, user, patch
    )


@router.post("/review/refresh")
async def refresh_review(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await onboarding_service.ensure_profile_review(
        db, request.app.state.mongo_db, user, force=True
    )


@router.post("/review/start-recommended")
async def start_recommended(
    request: Request,
    body: StartRecommendedRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = body.model_dump(exclude_none=True) if body else {}
    return await onboarding_service.start_recommended_track(
        db,
        request.app.state.mongo_db,
        user,
        request_id=request.headers.get("x-request-id"),
        subject=payload.get("subject"),
        track_type=payload.get("track_type"),
    )
