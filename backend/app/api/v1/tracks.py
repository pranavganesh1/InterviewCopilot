import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.gateway.llm import LLMGatewayError
from app.models.user import User
from app.services import track_service

router = APIRouter(prefix="/tracks", tags=["tracks"])

_HIDDEN_BANK_FIELDS = {"correct_index", "expected_value", "tolerance", "key_points"}


def _redact_track_payload(payload: dict) -> dict:
    """Keep answer keys in the database. Do not send them with the brief."""
    brief = payload.get("brief")
    if not isinstance(brief, dict) or not isinstance(brief.get("content"), dict):
        return payload
    content = dict(brief["content"])
    bank = []
    for question in content.get("question_bank") or []:
        if isinstance(question, dict):
            bank.append({k: v for k, v in question.items() if k not in _HIDDEN_BANK_FIELDS})
        else:
            bank.append(question)
    content["question_bank"] = bank
    return {**payload, "brief": {**brief, "content": content}}


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
    try:
        return _redact_track_payload(await track_service.create_track_with_brief(
            db,
            user,
            track_type=body.track_type,
            subject=body.subject,
            company=body.company,
            jd_text=body.jd_text,
        ))
    except LLMGatewayError as exc:
        # Free-tier rate limits surface as 503 with a retry hint, not a raw 500.
        raise HTTPException(
            status_code=503,
            detail="The LLM provider is rate-limited right now — please retry in a minute.",
        ) from exc


@router.get("")
async def list_tracks(
    include_archived: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await track_service.list_tracks(db, user, include_archived=include_archived)


@router.delete("/{track_id}")
async def delete_track(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await track_service.archive_track(db, user, track_id)
    except track_service.UnfinishedInterviewError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "unfinished_interview",
                "message": "Finish or close your unfinished interview first",
                "session_id": str(exc.session_id),
            },
        ) from None
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result


@router.post("/{track_id}/restore")
async def restore_track(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await track_service.restore_track(db, user, track_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result


@router.get("/{track_id}")
async def get_track(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await track_service.get_track_with_brief(db, user, track_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return _redact_track_payload(result)


@router.get("/{track_id}/brief")
async def get_brief(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await track_service.get_track_with_brief(db, user, track_id)
    if result is None or result["brief"] is None:
        raise HTTPException(status_code=404, detail="Brief not found")
    return _redact_track_payload(result)["brief"]
