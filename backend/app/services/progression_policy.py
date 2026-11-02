from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import ProgressionState

STRUGGLING_LEVELS = {"weak", "developing"}
GUIDED_UNLOCK_AFTER = 3


async def apply_progression(
    db: AsyncSession, track_id, report_content: dict, session_mode: str
) -> dict:
    """Update per-track progression from a completed session's report.

    Per LLD invariant 11 the agent does NOT own this transition — this policy
    code does. Only completed STRICT sessions count. UNLOCKED is permanent.
    """
    prog = (
        await db.execute(select(ProgressionState).where(ProgressionState.track_id == track_id))
    ).scalar_one_or_none()
    if prog is None:
        prog = ProgressionState(track_id=track_id)
        db.add(prog)
        await db.flush()

    if session_mode != "strict":
        return {"strict_completed": prog.strict_completed, "guided_state": prog.guided_state}

    prog.strict_completed += 1

    if prog.guided_state != "UNLOCKED" and prog.strict_completed >= GUIDED_UNLOCK_AFTER:
        levels = await _recent_levels(db, track_id, GUIDED_UNLOCK_AFTER)
        assessed = [lv for lv in levels if lv is not None]
        if assessed and sum(1 for lv in assessed if lv in STRUGGLING_LEVELS) > len(assessed) / 2:
            prog.guided_state = "UNLOCKED"

    await db.commit()
    return {"strict_completed": prog.strict_completed, "guided_state": prog.guided_state}


async def _recent_levels(db: AsyncSession, track_id, limit: int) -> list[str | None]:
    from app.models.feedback import FeedbackReport

    reports = (
        (
            await db.execute(
                select(FeedbackReport)
                .where(FeedbackReport.track_id == track_id)
                .order_by(FeedbackReport.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    levels: list[str | None] = []
    for r in reports:
        for comp in r.content.get("competency_assessments", []):
            levels.append(comp.get("level"))
    return levels
