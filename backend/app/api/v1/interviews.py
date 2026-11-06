import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.gateway.llm import LLMGatewayError
from app.models.user import User
from app.services import interview_service

router = APIRouter(tags=["interviews"])


class SubmitAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=20000)


class CreateSession(BaseModel):
    mode: Literal["strict", "guided"] = "strict"
    duration_minutes: int = Field(default=60, ge=15, le=240)


@router.get("/tracks/{track_id}/open-session")
async def open_session(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The unfinished session on this track, if one exists.

    Nothing else can discover it: the track payload does not include sessions.
    """
    result = await interview_service.get_open_session(db, user, track_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result


@router.post("/tracks/{track_id}/sessions", status_code=201)
async def start_session(
    track_id: uuid.UUID,
    request: Request,
    body: CreateSession | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await interview_service.start_session(
            db,
            user,
            track_id,
            mode=(body.mode if body else "strict"),
            duration_minutes=(body.duration_minutes if body else 60),
            mongo_db=getattr(request.app.state, "mongo_db", None),
        )
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail="The LLM provider is rate-limited right now — please retry in a minute.",
        ) from exc
    except LookupError as exc:
        detail = {
            "track_not_found": ("Track not found", 404),
            "brief_not_found": ("Track has no Interview Brief yet", 409),
        }.get(str(exc), ("Not found", 404))
        raise HTTPException(status_code=detail[1], detail=detail[0]) from None
    except ValueError as exc:
        if str(exc) == "invalid_mode":
            raise HTTPException(
                status_code=422, detail="mode must be 'strict' or 'guided'"
            ) from None
        raise
    except PermissionError as exc:
        if str(exc) == "guided_locked":
            raise HTTPException(
                status_code=403,
                detail="Guided mode is locked until progression policy unlocks it",
            ) from None
        if str(exc) == "track_archived":
            raise HTTPException(
                status_code=409,
                detail="This track is archived. Restore it before starting an interview.",
            ) from None
        raise


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
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await interview_service.submit_answer(
            db,
            user,
            session_id,
            body.answer,
            nc=getattr(request.app.state, "nats", None),
            mongo_db=getattr(request.app.state, "mongo_db", None),
        )
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail="The LLM provider is rate-limited right now — please retry in a minute.",
        ) from exc
    except LookupError as exc:
        if str(exc) == "deadline_passed":
            raise HTTPException(
                status_code=409,
                detail="The interview deadline has passed",
            ) from None
        if str(exc) == "no_open_question":
            raise HTTPException(
                status_code=409, detail="No open question — session not active"
            ) from None
        if str(exc) == "session_not_active":
            raise HTTPException(status_code=409, detail="Session is not active") from None
        raise HTTPException(status_code=404, detail="Session not found") from None


@router.post("/sessions/{session_id}/assistance")
async def request_assistance(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await interview_service.request_assistance(db, user, session_id)
    except LookupError as exc:
        detail = {
            "session_not_found": ("Session not found", 404),
            "session_not_active": ("Session is not active", 409),
            "no_open_question": ("No open question — assistance unavailable", 409),
            "assistance_exhausted": ("Maximum assistance level already granted", 409),
        }.get(str(exc), ("Not found", 404))
        raise HTTPException(status_code=detail[1], detail=detail[0]) from None
    except PermissionError as exc:
        if str(exc) == "assistance_not_allowed":
            raise HTTPException(
                status_code=403,
                detail="Assistance is only available in Guided mode",
            ) from None
        raise


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await interview_service.complete_session(
        db, user, session_id, nc=getattr(request.app.state, "nats", None)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result
