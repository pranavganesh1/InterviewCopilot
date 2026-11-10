import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ITEM_CATEGORIES_SET, ExtractedItem
from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.s3 import get_s3_client
from app.db.sqlalchemy import get_db
from app.gateway.llm import LLMGatewayError
from app.models.user import User
from app.services import readiness as readiness_service
from app.services.resume_service import ResumeUploadError, process_resume
from app.services import conversation_store
from app.services.vault_service import (
    build_profile_review_message,
    create_items,
    delete_item,
    list_items,
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


@router.post("/items")
async def add_item(
    body: ManualItem, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if body.category not in ITEM_CATEGORIES_SET:
        raise HTTPException(status_code=422, detail=f"Unknown category: {body.category}")
    created = await create_items(db, user.id, [ExtractedItem(**body.model_dump())], "manual")
    i = created[0]
    return {"id": str(i.id), "category": i.category, "title": i.title}


@router.patch("/items/{item_id}")
async def patch_item(
    item_id: uuid.UUID,
    body: VaultItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await update_item(
        db, user.id, item_id, title=body.title, details=body.details
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Vault item not found")
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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_item(db, user.id, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Vault item not found")
    return {"status": "ok"}


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
        # Seed coach review message so onboarding starts from extracted profile.
        items = await list_items(db, user.id)
        if items:
            await conversation_store.append_message(
                request.app.state.mongo_db,
                str(user.id),
                "assistant",
                build_profile_review_message(items),
            )
        return result
    except ResumeUploadError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"message": exc.message, "code": exc.code},
        ) from None
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "The model is busy right now — retry in a minute.",
                "code": "model_unavailable",
            },
        ) from exc
    except Exception:
        correlation_id = request_id
        log.exception(
            "resume_upload_unhandled",
            stage="api",
            error_class="unexpected",
            user_id=str(user.id),
            correlation_id=correlation_id,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Something went wrong uploading your resume. Please try again.",
                "code": "internal_error",
                "correlation_id": correlation_id,
            },
        ) from None


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
