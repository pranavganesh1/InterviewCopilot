import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.schemas.interviews import (
    CloseEmptyResult,
    OpenSessionResult,
    OpenSessionRow,
    SessionWithTurn,
    SessionWithTurns,
    TurnResult,
)
from app.db.sqlalchemy import get_db
from app.gateway.llm import LLMGatewayError, gateway_error_detail
from app.models.user import User
from app.services import interview_service

router = APIRouter(tags=["interviews"])


class SubmitAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=20000)


class CreateSession(BaseModel):
    mode: Literal["strict", "guided"] = "strict"
    duration_minutes: int = Field(default=60, ge=15, le=240)
    use_resume: bool = False
    focus_weak: bool = False
    persona_id: str = "balanced"
    claim_seeds: list[dict] = Field(default_factory=list, max_length=24)


@router.get("/me/open-sessions", response_model=list[OpenSessionRow])
async def list_my_open_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int | None = Query(default=None, ge=1, le=100),
):
    """Dashboard: unfinished interviews across the current user's tracks."""
    return await interview_service.list_open_sessions_for_user(db, user, limit=limit)


@router.get("/tracks/{track_id}/open-session", response_model=OpenSessionResult)
async def open_session(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Open sessions on this track (newest first). `session` is the newest.

    Nothing else can discover them: the track payload does not include sessions.
    """
    result = await interview_service.get_open_session(db, user, track_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result


@router.post(
    "/tracks/{track_id}/close-empty-sessions",
    response_model=CloseEmptyResult,
)
async def close_empty_sessions(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Abort open interviews on this track that have 0 answered turns."""
    try:
        return await interview_service.close_empty_sessions_for_track(db, user, track_id)
    except LookupError as exc:
        if str(exc) == "track_not_found":
            raise HTTPException(status_code=404, detail="Track not found") from None
        raise


@router.post("/tracks/{track_id}/sessions", status_code=201, response_model=SessionWithTurn)
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
            use_resume=bool(body.use_resume) if body else False,
            focus_weak=bool(body.focus_weak) if body else False,
            persona_id=(body.persona_id if body else "balanced"),
            claim_seeds=(body.claim_seeds if body else None),
            mongo_db=getattr(request.app.state, "mongo_db", None),
            request_id=request.headers.get("x-request-id"),
        )
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail=gateway_error_detail(exc),
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
        if str(exc) == "invalid_persona":
            raise HTTPException(
                status_code=422,
                detail="persona_id must be one of: balanced, architect, hiring_manager, academic",
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
        if str(exc) == "open_session_in_progress":
            raise HTTPException(
                status_code=409,
                detail="An unfinished interview already has answers. Resume or finish it first.",
            ) from None
        raise


@router.post("/sessions/{session_id}/abort")
async def abort_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close an unfinished session without scoring (rows kept)."""
    result = await interview_service.abort_session(db, user, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/sessions/{session_id}", response_model=SessionWithTurns)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await interview_service.get_session(db, user, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/{session_id}/turns", response_model=TurnResult)
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
    except LLMGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail="The LLM provider is rate-limited right now — please retry in a minute.",
        ) from exc
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
