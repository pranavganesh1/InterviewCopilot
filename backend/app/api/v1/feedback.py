import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import feedback_service

router = APIRouter(tags=["feedback"])


@router.get("/sessions/{session_id}/report")
async def get_report(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await feedback_service.get_report_for_session(db, user.id, session_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report not ready — it is generated asynchronously after the interview",
        )
    return report


@router.get("/tracks/{track_id}/progression")
async def get_progression(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await feedback_service.get_progression_for_track(db, user.id, track_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result
