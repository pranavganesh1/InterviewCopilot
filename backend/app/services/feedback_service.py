import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.feedback_agent import FeedbackReportContent, build_feedback_graph
from app.agents.question_quality import practice_label_for
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.feedback import FeedbackReport, ProgressionState
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.services.feedback_report_builder import (
    build_report_from_saved_evaluations,
    enrich_assessments_with_turns,
    performance_level_from_score,
)
from app.services.progression_policy import apply_progression

log = get_logger(__name__)

COVERAGE_POINTS = {"none": 0, "partial": 50, "good": 75, "excellent": 100}


async def run_feedback_agent(**kwargs):
    from app.agents.feedback_agent import run_feedback_agent as _run

    return await _run(**kwargs)


def overall_score_from_content(content: dict | None) -> int | None:
    """Average coverage score across assessed (submitted) questions only."""
    if not content:
        return None
    items = content.get("question_assessments") or []
    if not items:
        return None
    total = sum(COVERAGE_POINTS.get(str(q.get("coverage", "")).lower(), 0) for q in items)
    return int(round(total / len(items)))


async def process_session_feedback(db: AsyncSession, session_id) -> dict:
    """Run feedback for a completed session and persist the report.

    Idempotent: one report per session (reprocessing replaces it).
    Only submitted answers are assessed. The report is always grounded in
    saved per-turn evaluations; the LLM agent enriches when available.
    """
    sid = uuid.UUID(str(session_id))
    session = await db.get(InterviewSession, sid)
    if session is None:
        log.error(
            "feedback_session_lookup_miss",
            session_id=str(session_id),
            database=get_settings().database_url.rsplit("/", 1)[-1],
        )
        raise LookupError("session_not_found")
    if session.status != "completed":
        log.info(
            "feedback_session_not_completed",
            session_id=str(session.id),
            status=session.status,
        )
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
    answered = [t for t in turns if t.answer is not None and str(t.answer).strip()]

    track = await db.get(Track, session.track_id)
    brief = (
        await db.execute(
            select(InterviewBrief)
            .where(InterviewBrief.track_id == session.track_id)
            .order_by(InterviewBrief.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    brief_content = brief.content if brief else {}
    max_turns = get_settings().interview_max_turns

    # Reliable base: consolidate evaluations already saved on each turn.
    base = build_report_from_saved_evaluations(
        session=session,
        answered_turns=answered,
        brief_content=brief_content,
        max_turns=max_turns,
    )
    content = base.model_dump()

    payload = {
        "session_mode": session.mode,
        "track_subject": track.subject if track else "",
        "brief": brief_content,
        "answered_count": len(answered),
        "total_turns_created": len(turns),
        "max_turns": max_turns,
        "evaluate_only_submitted_answers": True,
        "saved_evaluations": [
            {
                "turn_index": t.turn_index,
                "question_area": t.question_area,
                "coverage": t.evaluation_coverage,
                "strengths": t.evaluation_strengths or [],
                "gaps": t.evaluation_gaps or [],
                "detail": t.evaluation_detail or {},
            }
            for t in answered
        ],
        "transcript": [
            {
                "turn_index": t.turn_index,
                "question_area": t.question_area,
                "question": t.question,
                "answer": t.answer or "",
                "assisted": bool(t.assisted),
                "assistance_level": t.assistance_level or 0,
            }
            for t in answered
        ],
    }

    try:
        graph = build_feedback_graph(turn_runner=run_feedback_agent)
        result = await graph.ainvoke(
            {
                "payload": payload,
                "meta": {
                    "user_id": str(session.user_id),
                    "track_id": str(session.track_id),
                    "session_id": str(session.id),
                },
            }
        )
        enriched = FeedbackReportContent.model_validate(result["report"]).model_dump()
        # Keep question assessments from saved evaluations when the agent
        # returns fewer (it must not invent unanswered questions).
        if not enriched.get("question_assessments") and content.get("question_assessments"):
            enriched["question_assessments"] = content["question_assessments"]
        content = enriched
        log.info(
            "feedback_agent_enriched",
            session_id=str(session.id),
            answered=len(answered),
        )
    except Exception as exc:
        # Transient LLM / infra failures: still persist the consolidated report.
        log.warning(
            "feedback_agent_fallback_to_saved_evaluations",
            session_id=str(session.id),
            error=str(exc)[:200],
        )

    content = enrich_assessments_with_turns(content, answered)
    label = practice_label_for(brief_content if isinstance(brief_content, dict) else {})
    if label:
        content["practice_label"] = label
    try:
        from app.agents.persona import get_persona
        from app.services import probe as probe_service

        persona = get_persona(
            probe_service.session_opts_from_plan(session.question_plan).get("persona_id")
        )
        content["persona_id"] = persona.id
        content["persona_name"] = persona.name
    except Exception as exc:
        log.warning(
            "persona_report_enrich_failed",
            session_id=str(session.id),
            error=str(exc)[:200],
        )
    # Drop anything the agent invented for a question the candidate never answered.
    answered_indexes = {t.turn_index for t in answered}
    content["question_assessments"] = [
        row
        for row in (content.get("question_assessments") or [])
        if int(row.get("turn_index") or 0) in answered_indexes
    ]
    try:
        from app.services import weakness as weakness_service
        from app.services.interview_service import _track_answered_turns

        prior_turns, session_ids = await _track_answered_turns(
            db, session.user_id, session.track_id
        )
        # Include this session's answered turns (already in prior after commit path).
        summary = weakness_service.aggregate_turns(prior_turns, session_order=session_ids)
        content["diagnostics"] = weakness_service.build_diagnostics(summary)
    except Exception as exc:
        log.warning(
            "diagnostics_build_failed",
            session_id=str(session.id),
            error=str(exc)[:200],
        )

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
    log.info(
        "feedback_report_persisted",
        session_id=str(session.id),
        report_id=str(report.id),
        user_id=str(session.user_id),
        answered=len(answered),
    )
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


async def get_weaknesses_for_track(db: AsyncSession, user_id, track_id) -> dict | None:
    track = await db.get(Track, track_id)
    if track is None or track.user_id != user_id:
        return None
    from app.services import weakness as weakness_service
    from app.services.interview_service import _track_answered_turns

    turns, session_ids = await _track_answered_turns(db, user_id, track_id)
    summary = weakness_service.aggregate_turns(turns, session_order=session_ids)
    top = (summary.get("weak") or [])[:3]
    return {
        "track_id": str(track_id),
        "has_data": bool(summary.get("has_data")),
        "weak": summary.get("weak") or [],
        "improving": summary.get("improving") or [],
        "mastered": summary.get("mastered") or [],
        "top_weak": [
            {
                "concept": c["concept"],
                "status": c["status"],
                "last_coverage": c.get("last_coverage"),
            }
            for c in top
        ],
        "recommended_practice": weakness_service.recommended_practice(
            (summary.get("weak") or []) + (summary.get("improving") or [])
        ),
    }


async def list_assessments_for_user(db: AsyncSession, user_id) -> dict:
    """Completed assessments for the profile dashboard (reports only — no unfinished)."""
    rows = (
        await db.execute(
            select(FeedbackReport, Track, InterviewSession)
            .join(Track, Track.id == FeedbackReport.track_id)
            .join(InterviewSession, InterviewSession.id == FeedbackReport.session_id)
            .where(FeedbackReport.user_id == user_id)
            .order_by(FeedbackReport.created_at.desc())
        )
    ).all()

    assessments = []
    strength_counter: Counter[str] = Counter()
    improve_counter: Counter[str] = Counter()
    recommend_counter: Counter[str] = Counter()
    scores: list[int] = []
    questions_attempted = 0

    for report, track, session in rows:
        content = report.content if isinstance(report.content, dict) else {}
        archived = track.archived_at is not None
        attempted = len(content.get("question_assessments") or [])
        score = overall_score_from_content(content)
        if not archived:
            questions_attempted += attempted
            if score is not None:
                scores.append(score)

        if not archived:
            for s in content.get("strengths") or []:
                if s:
                    strength_counter[str(s)] += 1
            for s in content.get("improvement_areas") or []:
                if s:
                    improve_counter[str(s)] += 1
            for s in content.get("recommendations") or []:
                if s:
                    recommend_counter[str(s)] += 1
        if not archived:
            for comp in content.get("competency_assessments") or []:
                name = comp.get("competency_name")
                level = comp.get("level")
                if not name:
                    continue
                if level in ("strong", "solid"):
                    strength_counter[str(name)] += 2
                elif level in ("weak", "developing"):
                    improve_counter[str(name)] += 2

        assessments.append(
            {
                "report_id": str(report.id),
                "session_id": str(report.session_id),
                "track_id": str(report.track_id),
                "track_subject": track.subject,
                "created_at": report.created_at.isoformat(),
                "session_mode": content.get("session_mode") or session.mode,
                "coverage_status": content.get("coverage_status") or "PARTIAL",
                "overall_score": score,
                "questions_attempted": attempted,
                "max_turns": get_settings().interview_max_turns,
                "status": "completed",
                "track_archived": archived,
                "summary_overview": content.get("summary_overview") or "",
                "strengths": content.get("strengths") or [],
                "improvement_areas": content.get("improvement_areas") or [],
            }
        )

    return {
        "dashboard": {
            "completed_interviews": sum(1 for item in assessments if not item["track_archived"]),
            "average_score": int(round(sum(scores) / len(scores))) if scores else None,
            "total_questions_attempted": questions_attempted,
            "strongest_skills": [k for k, _ in strength_counter.most_common(5)],
            "skills_needing_improvement": [k for k, _ in improve_counter.most_common(5)],
            "recommended_topics": [k for k, _ in recommend_counter.most_common(5)],
        },
        "assessments": assessments,
    }


def _report_dict(report: FeedbackReport) -> dict:
    content = report.content if isinstance(report.content, dict) else {}
    score = overall_score_from_content(content)
    return {
        "id": str(report.id),
        "session_id": str(report.session_id),
        "content": content,
        "overall_score": score,
        "performance_level": performance_level_from_score(score),
        "questions_attempted": len(content.get("question_assessments") or []),
        "max_turns": get_settings().interview_max_turns,
        "created_at": report.created_at.isoformat(),
    }
