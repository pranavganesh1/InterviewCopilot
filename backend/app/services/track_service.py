import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.question_quality import subject_problem
from app.agents.track_creator import build_track_creator_graph
from app.models.interview import InterviewSession
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.services.vault_service import vault_summary


async def run_track_creator_turn(**kwargs):
    from app.agents.track_creator import run_track_creator_turn as _run

    return await _run(**kwargs)


async def run_bank_builder_turn(**kwargs):
    from app.agents.track_creator import run_bank_builder_turn as _run

    return await _run(**kwargs)


async def run_bank_judge_turn(**kwargs):
    from app.agents.track_creator import run_bank_judge_turn as _run

    return await _run(**kwargs)


async def run_bank_regeneration_turn(**kwargs):
    from app.agents.track_creator import run_bank_builder_turn as _run

    return await _run(**kwargs)


async def build_track_creator_brief(
    *, objective: dict, vault_summary: list[dict], meta: dict | None = None
) -> dict:
    """Author the brief + validated question bank (no DB). Testable in isolation."""
    problem = subject_problem(str(objective.get("subject") or ""))
    if problem:
        return {
            "summary": problem,
            "clarification_message": problem,
            "preparation_plan": [],
            "competencies": [],
            "question_areas": [],
            "candidate_angle_notes": "",
            "question_bank": [],
        }
    graph = build_track_creator_graph(
        turn_runner=run_track_creator_turn,
        bank_runner=run_bank_builder_turn,
        judge_runner=run_bank_judge_turn,
        regen_runner=run_bank_regeneration_turn,
    )
    result = await graph.ainvoke(
        {"objective": objective, "vault_summary": vault_summary, "meta": meta or {}}
    )
    return result["brief"]


async def create_track_with_brief(
    db: AsyncSession,
    user: User,
    *,
    track_type: str,
    subject: str,
    company: str | None = None,
    jd_text: str | None = None,
    request_id: str | None = None,
) -> dict:
    # Author FIRST: if the LLM fails, nothing is saved — the user gets a clean
    # 503 and can retry. (Saving the track first used to leave orphans with
    # "no Interview Brief" on every quota failure — M11 finding.)
    content = await build_track_creator_brief(
        objective={
            "track_type": track_type,
            "subject": subject,
            "company": company,
            "jd_text": jd_text,
        },
        vault_summary=await vault_summary(db, user.id),
        meta={"user_id": str(user.id)},
    )

    track = Track(
        user_id=user.id,
        track_type=track_type,
        subject=subject,
        company=company,
        jd_text=jd_text,
    )
    db.add(track)
    await db.commit()
    await db.refresh(track)

    brief = InterviewBrief(track_id=track.id, version=1, content=content)
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return {"track": _track_dict(track), "brief": _brief_dict(brief)}


class UnfinishedInterviewError(Exception):
    def __init__(self, session_id: uuid.UUID):
        self.session_id = session_id


async def list_tracks(
    db: AsyncSession, user: User, *, include_archived: bool = False
) -> list[dict]:
    stmt = select(Track).where(Track.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Track.archived_at.is_(None))
    result = await db.execute(stmt.order_by(Track.created_at.desc()))
    tracks = []
    for t in result.scalars().all():
        latest = await _latest_brief(db, t.id)
        d = _track_dict(t)
        d["brief_version"] = latest.version if latest else 0
        tracks.append(d)
    return tracks


async def _owned_track(db: AsyncSession, user: User, track_id: uuid.UUID) -> Track | None:
    track = await db.get(Track, track_id)
    if track is None or track.user_id != user.id:
        return None
    return track


async def archive_track(db: AsyncSession, user: User, track_id: uuid.UUID) -> dict | None:
    """Hide a track from the owner's lists. Rows are left in place."""
    track = await _owned_track(db, user, track_id)
    if track is None:
        return None
    if track.archived_at is None:
        # Close any unfinished interview: the user owns the call — deleting the
        # track is an explicit decision, not something to gate behind a dialog.
        await db.execute(
            update(InterviewSession)
            .where(
                InterviewSession.track_id == track.id,
                InterviewSession.user_id == user.id,
                InterviewSession.status == "in_progress",
            )
            .values(status="aborted", completed_at=datetime.now(UTC))
        )
        track.archived_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(track)
    return {"track": _track_dict(track)}


async def restore_track(db: AsyncSession, user: User, track_id: uuid.UUID) -> dict | None:
    track = await _owned_track(db, user, track_id)
    if track is None:
        return None
    if track.archived_at is not None:
        track.archived_at = None
        await db.commit()
        await db.refresh(track)
    return {"track": _track_dict(track)}


async def get_track_with_brief(db: AsyncSession, user: User, track_id: uuid.UUID) -> dict | None:
    track = await db.get(Track, track_id)
    if track is None or track.user_id != user.id:
        return None
    latest = await _latest_brief(db, track.id)
    return {"track": _track_dict(track), "brief": _brief_dict(latest) if latest else None}


async def _latest_brief(db: AsyncSession, track_id) -> InterviewBrief | None:
    result = await db.execute(
        select(InterviewBrief)
        .where(InterviewBrief.track_id == track_id)
        .order_by(InterviewBrief.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _track_dict(t: Track) -> dict:
    return {
        "id": str(t.id),
        "track_type": t.track_type,
        "subject": t.subject,
        "company": t.company,
        "status": t.status,
        "archived": t.archived_at is not None,
        "archived_at": t.archived_at.isoformat() if t.archived_at else None,
        "created_at": t.created_at.isoformat(),
    }


def _brief_dict(b: InterviewBrief) -> dict:
    return {
        "version": b.version,
        "content": b.content,
        "created_at": b.created_at.isoformat(),
    }
