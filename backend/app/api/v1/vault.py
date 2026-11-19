import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ITEM_CATEGORIES_SET, ExtractedItem
from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.s3 import get_s3_client
from app.db.sqlalchemy import get_db
from app.gateway.llm import LLMCause, LLMGatewayError
from app.models.user import User
from app.services import onboarding_service
from app.services import readiness as readiness_service
from app.services.resume_service import (
    ResumeUploadError,
    process_resume,
    reprocess_latest_resume,
)
from app.services.vault_service import (
    apply_enrichment,
    create_items,
    delete_item,
    find_near_duplicates,
    list_items,
    list_resume_sourced_items,
    reset_resume_sourced_items,
    resolve_duplicate_pair,
    suggest_keep_side,
    update_item,
)

log = get_logger(__name__)

router = APIRouter(prefix="/vault", tags=["vault"])


class ManualItem(BaseModel):
    category: str
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


class VaultItemUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    details: dict[str, str] | None = None


class ReadinessRequest(BaseModel):
    refresh: bool = False


class DuplicateResolveRequest(BaseModel):
    keep_id: uuid.UUID
    discard_id: uuid.UUID
    merge_details: bool = True


class EnrichmentApplyRequest(BaseModel):
    item_id: uuid.UUID
    details: dict[str, str] = {}
    only_fill_empty: bool = True


class ResumeResetRequest(BaseModel):
    confirm: bool = False
    confirm_phrase: str = ""


@router.get("/items")
async def get_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await list_items(db, user.id)
    return [
        {
            "id": str(i.id),
            "category": i.category,
            "title": i.title,
            "details": i.details,
            "source": i.source,
        }
        for i in items
    ]


async def _refresh_review_after_vault_change(
    request: Request, db: AsyncSession, user: User
) -> None:
    """Keep post-onboarding review aligned with vault corrections."""
    if user.onboarding_completed_at is None:
        return
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is None:
        return
    await onboarding_service.ensure_profile_review(db, mongo, user)


@router.post("/items")
async def add_item(
    body: ManualItem,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.category not in ITEM_CATEGORIES_SET:
        raise HTTPException(status_code=422, detail=f"Unknown category: {body.category}")
    created = await create_items(db, user.id, [ExtractedItem(**body.model_dump())], "manual")
    i = created[0]
    await _refresh_review_after_vault_change(request, db, user)
    return {"id": str(i.id), "category": i.category, "title": i.title}


@router.patch("/items/{item_id}")
async def patch_item(
    item_id: uuid.UUID,
    body: VaultItemUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await update_item(
        db, user.id, item_id, title=body.title, details=body.details
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Vault item not found")
    await _refresh_review_after_vault_change(request, db, user)
    return {
        "id": str(item.id),
        "category": item.category,
        "title": item.title,
        "details": item.details or {},
        "source": item.source,
    }


@router.delete("/items/{item_id}")
async def remove_item(
    item_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_item(db, user.id, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Vault item not found")
    await _refresh_review_after_vault_change(request, db, user)
    return {"status": "ok"}


def _resume_http_error(exc: Exception, *, request_id: str, user_id: str):
    if isinstance(exc, ResumeUploadError):
        raise HTTPException(
            status_code=exc.status,
            detail={"message": exc.message, "code": exc.code},
        ) from None
    if isinstance(exc, LLMGatewayError):
        if getattr(exc, "cause", None) == LLMCause.schema_rejected:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        "We couldn't structure this resume into profile items. "
                        "Please try again, or add items manually in onboarding."
                    ),
                    "code": "resume_structure_failed",
                    "cause": LLMCause.schema_rejected.value,
                },
            ) from exc
        raise HTTPException(
            status_code=503,
            detail={
                "message": "The model is busy right now — retry in a minute.",
                "code": "model_unavailable",
            },
        ) from exc
    log.exception(
        "resume_upload_unhandled",
        stage="api",
        error_class="unexpected",
        user_id=user_id,
        correlation_id=request_id,
    )
    raise HTTPException(
        status_code=500,
        detail={
            "message": "Something went wrong uploading your resume. Please try again.",
            "code": "internal_error",
            "correlation_id": request_id,
        },
    ) from None


@router.post("/resume")
async def upload_resume(
    request: Request,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    data = await file.read()
    s3 = get_s3_client()
    try:
        result = await process_resume(
            db,
            s3,
            user,
            file.filename or "resume.pdf",
            data,
            content_type=file.content_type,
            request_id=request_id,
        )
        items = await list_items(db, user.id)
        mongo = getattr(request.app.state, "mongo_db", None)
        welcome_seeded = False
        conversation_id = None
        if mongo is not None:
            seeded = await onboarding_service.seed_resume_welcome(
                mongo, str(user.id), items, sync_result=result
            )
            welcome_seeded = bool(seeded.get("seeded"))
            conversation_id = seeded.get("conversation_id")
        await _refresh_review_after_vault_change(request, db, user)
        return {
            **result,
            "welcome_seeded": welcome_seeded,
            "conversation_id": conversation_id,
            "conversation_started": welcome_seeded,
        }
    except (ResumeUploadError, LLMGatewayError, Exception) as exc:
        _resume_http_error(exc, request_id=request_id, user_id=str(user.id))


@router.post("/resume/reprocess")
async def reprocess_resume(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run extraction on the latest stored resume; sync against Profile Vault."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    s3 = get_s3_client()
    try:
        result = await reprocess_latest_resume(
            db, s3, user, request_id=request_id
        )
        await _refresh_review_after_vault_change(request, db, user)
        return result
    except (ResumeUploadError, LLMGatewayError, Exception) as exc:
        _resume_http_error(exc, request_id=request_id, user_id=str(user.id))


@router.get("/duplicates")
async def get_duplicates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await list_items(db, user.id)
    pairs = find_near_duplicates(items)
    return {
        "pairs": [
            {**pair, "suggested_keep": suggest_keep_side(pair)} for pair in pairs
        ],
        "count": len(pairs),
        "note": (
            "Suspected duplicates for your review. Nothing is deleted until you approve."
        ),
    }


@router.post("/duplicates/resolve")
async def resolve_duplicate(
    body: DuplicateResolveRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kept = await resolve_duplicate_pair(
        db,
        user.id,
        keep_id=body.keep_id,
        discard_id=body.discard_id,
        merge_details=body.merge_details,
    )
    if kept is None:
        raise HTTPException(
            status_code=404,
            detail="Duplicate pair not found or not owned by this account.",
        )
    await _refresh_review_after_vault_change(request, db, user)
    return {"status": "resolved", "kept": kept}


@router.post("/enrichment/apply")
async def enrichment_apply(
    body: EnrichmentApplyRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await apply_enrichment(
        db,
        user.id,
        item_id=body.item_id,
        details=body.details,
        only_fill_empty=body.only_fill_empty,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Vault item not found")
    await _refresh_review_after_vault_change(request, db, user)
    return {
        "id": str(item.id),
        "category": item.category,
        "title": item.title,
        "details": item.details or {},
        "source": item.source,
    }


@router.get("/resume-data/reset-preview")
async def resume_reset_preview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_resume_sourced_items(db, user.id)
    return {
        "count": len(rows),
        "items": [
            {
                "id": str(r.id),
                "category": r.category,
                "title": r.title,
                "source": r.source,
            }
            for r in rows
        ],
        "scope": (
            "Only Profile Vault rows with source=resume for your account. "
            "Manual entries, chat-added items, interviews, answers, reports, "
            "and account data are not included."
        ),
        "confirm_phrase": "RESET RESUME DATA",
    }


@router.post("/resume-data/reset")
async def resume_reset(
    body: ResumeResetRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.confirm or body.confirm_phrase.strip().upper() != "RESET RESUME DATA":
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Confirmation required. Set confirm=true and confirm_phrase="
                    "'RESET RESUME DATA'."
                ),
                "code": "confirmation_required",
            },
        )
    result = await reset_resume_sourced_items(db, user.id)
    await _refresh_review_after_vault_change(request, db, user)
    return {"status": "ok", **result}


@router.post("/readiness")
async def vault_readiness(
    request: Request,
    body: ReadinessRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only resume readiness audit. Private; admin UIs do not surface this."""
    refresh = bool(body.refresh) if body else False
    items = await list_items(db, user.id)
    mongo_db = getattr(request.app.state, "mongo_db", None)
    try:
        result = await readiness_service.run_readiness(
            items=items,
            user_id=str(user.id),
            mongo_db=mongo_db,
            refresh=refresh,
        )
    except PermissionError as exc:
        if str(exc) == "rate_limited":
            raise HTTPException(
                status_code=429,
                detail="Please wait a moment before running another readiness check.",
            ) from None
        raise
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail="The model is busy right now — retry in a minute.",
        ) from exc
    return result.model_dump()
