import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import interview_service

router = APIRouter(tags=["interviews"])


class SubmitAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=20000)


class CreateSession(BaseModel):
    mode: str = "strict"


@router.post("/tracks/{track_id}/sessions", status_code=201)
async def start_session(
    track_id: uuid.UUID,
    body: CreateSession | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await interview_service.start_session(
            db, user, track_id, mode=(body.mode if body else "strict")
        )
    except LookupError as exc:
        detail = {
            "track_not_found": ("Track not found", 404),
            "brief_not_found": ("Track has no Interview Brief yet", 409),
        }.get(str(exc), ("Not found", 404))
        raise HTTPException(status_code=detail[1], detail=detail[0]) from None


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await interview_service.get_session(db, user, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/{session_id}/turns")
async def submit_turn(
    session_id: uuid.UUID,
    body: SubmitAnswer,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await interview_service.submit_answer(db, user, session_id, body.answer)
    except LookupError as exc:
        if str(exc) == "no_open_question":
            raise HTTPException(
                status_code=409, detail="No open question — session not active"
            ) from None
        raise HTTPException(status_code=404, detail="Session not found") from None


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await interview_service.complete_session(db, user, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result
