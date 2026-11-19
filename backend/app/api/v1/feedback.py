import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import career_intelligence as career_intel
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


@router.get("/me/assessments")
async def list_my_assessments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Profile dashboard: completed interview reports owned by the current user."""
    return await feedback_service.list_assessments_for_user(db, user.id)


@router.get("/me/career-intelligence")
async def get_career_intelligence(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deterministic career readiness from stored evaluations (no LLM on load)."""
    mongo_db = getattr(request.app.state, "mongo_db", None)
    claim_seeds: list = []
    try:
        # Prefer cached vault readiness seeds when available (no forced LLM refresh).
        from app.services import readiness as readiness_service
        from app.services.vault_service import list_items

        items = await list_items(db, user.id)
        content_hash = readiness_service.vault_content_hash(items)
        cached = await readiness_service._cache_get(mongo_db, str(user.id), content_hash)
        if isinstance(cached, dict):
            claim_seeds = list(cached.get("claim_seeds") or [])[:12]
    except Exception:
        claim_seeds = []
    return await career_intel.get_career_intelligence_for_user(
        db, user.id, mongo_db=mongo_db, claim_seeds=claim_seeds
    )


@router.get("/tracks/{track_id}/weaknesses")
async def get_track_weaknesses(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Derived concept weaknesses for the track owner (empty when not enough data)."""
    result = await feedback_service.get_weaknesses_for_track(db, user.id, track_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result
