import asyncio

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ITEM_CATEGORIES_SET, ExtractedItem
from app.api.deps import get_current_user
from app.db.s3 import ensure_bucket, get_s3_client
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services.resume_service import MAX_RESUME_BYTES, process_resume
from app.services.vault_service import create_items, list_items

router = APIRouter(prefix="/vault", tags=["vault"])


class ManualItem(BaseModel):
    category: str
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


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


@router.post("/resume")
async def upload_resume(
    file: UploadFile, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only PDF resumes are supported")
    data = await file.read()
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume exceeds 10 MB")
    s3 = get_s3_client()
    await asyncio.to_thread(ensure_bucket, s3, "resumes")
    return await process_resume(db, s3, user, file.filename or "resume.pdf", data)
