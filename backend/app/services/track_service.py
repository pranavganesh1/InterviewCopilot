import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.track_creator import build_track_creator_graph
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


async def build_track_creator_brief(*, objective: dict, vault_summary: list[dict]) -> dict:
    """Author the brief + validated question bank (no DB). Testable in isolation."""
    graph = build_track_creator_graph(
        turn_runner=run_track_creator_turn,
        bank_runner=run_bank_builder_turn,
        judge_runner=run_bank_judge_turn,
        regen_runner=run_bank_regeneration_turn,
    )
    result = await graph.ainvoke({"objective": objective, "vault_summary": vault_summary})
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

    content = await build_track_creator_brief(
        objective={
            "track_type": track_type,
            "subject": subject,
            "company": company,
            "jd_text": jd_text,
        },
        vault_summary=await vault_summary(db, user.id),
    )

    brief = InterviewBrief(track_id=track.id, version=1, content=content)
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return {"track": _track_dict(track), "brief": _brief_dict(brief)}


async def list_tracks(db: AsyncSession, user: User) -> list[dict]:
    result = await db.execute(
        select(Track).where(Track.user_id == user.id).order_by(Track.created_at.desc())
    )
    tracks = []
    for t in result.scalars().all():
        latest = await _latest_brief(db, t.id)
        d = _track_dict(t)
        d["brief_version"] = latest.version if latest else 0
        tracks.append(d)
    return tracks


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
        "created_at": t.created_at.isoformat(),
    }


def _brief_dict(b: InterviewBrief) -> dict:
    return {
        "version": b.version,
        "content": b.content,
        "created_at": b.created_at.isoformat(),
    }
