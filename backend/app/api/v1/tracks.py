import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import track_service

router = APIRouter(prefix="/tracks", tags=["tracks"])


class CreateTrack(BaseModel):
    track_type: Literal["topic", "role", "company_jd"]
    subject: str = Field(max_length=255)
    company: str | None = Field(default=None, max_length=255)
    jd_text: str | None = Field(default=None, max_length=20000)


@router.post("", status_code=201)
async def create_track(
    body: CreateTrack,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.track_type == "company_jd" and not body.jd_text:
        raise HTTPException(status_code=422, detail="company_jd tracks require jd_text")
    return await track_service.create_track_with_brief(
        db,
        user,
        track_type=body.track_type,
        subject=body.subject,
        company=body.company,
        jd_text=body.jd_text,
    )


@router.get("")
async def list_tracks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await track_service.list_tracks(db, user)


@router.get("/{track_id}")
async def get_track(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await track_service.get_track_with_brief(db, user, track_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result


@router.get("/{track_id}/brief")
async def get_brief(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await track_service.get_track_with_brief(db, user, track_id)
    if result is None or result["brief"] is None:
        raise HTTPException(status_code=404, detail="Brief not found")
    return result["brief"]
