import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.feedback_agent import FeedbackReportContent, build_feedback_graph
from app.models.feedback import FeedbackReport, ProgressionState
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.services.progression_policy import apply_progression


async def run_feedback_agent(**kwargs):
    from app.agents.feedback_agent import run_feedback_agent as _run

    return await _run(**kwargs)


async def process_session_feedback(db: AsyncSession, session_id) -> dict:
    """Run the Feedback Agent over a completed session and persist the report.

    Idempotent: one report per session (reprocessing replaces it).
    """
    session = await db.get(InterviewSession, uuid.UUID(str(session_id)))
    if session is None:
        raise LookupError("session_not_found")
    if session.status != "completed":
        return {"skipped": "session_not_completed"}

    turns = (
        (
            await db.execute(
                select(SessionTurn)
                .where(SessionTurn.session_id == session.id)
                .order_by(SessionTurn.turn_index)
            )
        )
        .scalars()
        .all()
    )

    track = await db.get(Track, session.track_id)
    brief = (
        await db.execute(
            select(InterviewBrief)
            .where(InterviewBrief.track_id == session.track_id)
            .order_by(InterviewBrief.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    payload = {
        "session_mode": session.mode,
        "track_subject": track.subject if track else "",
        "brief": brief.content if brief else {},
        "transcript": [
            {
                "turn_index": t.turn_index,
                "question_area": t.question_area,
                "question": t.question,
                "answer": t.answer or "",
            }
            for t in turns
        ],
    }

    graph = build_feedback_graph(turn_runner=run_feedback_agent)
    result = await graph.ainvoke({"payload": payload})
    content = FeedbackReportContent.model_validate(result["report"]).model_dump()

    existing = (
        await db.execute(select(FeedbackReport).where(FeedbackReport.session_id == session.id))
    ).scalar_one_or_none()
    if existing is None:
        report = FeedbackReport(
            session_id=session.id,
            track_id=session.track_id,
            user_id=session.user_id,
            content=content,
        )
        db.add(report)
    else:
        existing.content = content
        report = existing
    await db.commit()
    await db.refresh(report)

    progression = await apply_progression(db, session.track_id, content, session.mode)
    return {"report": _report_dict(report), "progression": progression}


async def get_report_for_session(db: AsyncSession, user_id, session_id) -> dict | None:
    session = await db.get(InterviewSession, session_id)
    if session is None or session.user_id != user_id:
        return None
    report = (
        await db.execute(select(FeedbackReport).where(FeedbackReport.session_id == session.id))
    ).scalar_one_or_none()
    if report is None:
        return None
    return _report_dict(report)


async def get_progression_for_track(db: AsyncSession, user_id, track_id) -> dict | None:
    track = await db.get(Track, track_id)
    if track is None or track.user_id != user_id:
        return None
    prog = (
        await db.execute(select(ProgressionState).where(ProgressionState.track_id == track_id))
    ).scalar_one_or_none()
    return {
        "track_id": str(track_id),
        "strict_completed": prog.strict_completed if prog else 0,
        "guided_state": prog.guided_state if prog else "LOCKED",
    }


def _report_dict(report: FeedbackReport) -> dict:
    return {
        "id": str(report.id),
        "session_id": str(report.session_id),
        "content": report.content,
        "created_at": report.created_at.isoformat(),
    }
