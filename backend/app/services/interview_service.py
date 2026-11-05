import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.assistance import (
    generate_assistance,
    is_coding_question,
    label_for_level,
    max_level_for_question,
    next_assistance_level,
)
from app.agents.interviewer import TurnDecision, build_interviewer_graph
from app.agents.question_plan import build_question_plan
from app.core.config import get_settings
from app.models.interview import InterviewSession, SessionTurn
from app.models.user import User
from app.services.events import publish_feedback_job
from app.services.progression_policy import VALID_MODES, guided_unlocked
from app.services.track_service import get_track_with_brief


async def run_interviewer_turn(**kwargs):
    from app.agents.interviewer import run_interviewer_turn as _run

    return await _run(**kwargs)


async def run_assistance_turn(**kwargs):
    return await generate_assistance(**kwargs)


def _graph():
    return build_interviewer_graph(turn_runner=run_interviewer_turn)


async def start_session(db: AsyncSession, user: User, track_id, mode: str = "strict") -> dict:
    track_brief = await get_track_with_brief(db, user, track_id)
    if track_brief is None:
        raise LookupError("track_not_found")
    if track_brief["brief"] is None:
        raise LookupError("brief_not_found")

    mode = (mode or "strict").lower()
    if mode not in VALID_MODES:
        raise ValueError("invalid_mode")
    if mode == "guided" and not await guided_unlocked(db, track_id):
        raise PermissionError("guided_locked")

    brief_content = track_brief["brief"]["content"]
    plan = await build_question_plan(brief_content, get_settings().interview_max_turns)
    session = InterviewSession(
        track_id=track_id,
        user_id=user.id,
        mode=mode,
        question_plan=plan,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    decision = await _decide(db, session, brief_content, last_answer=None)
    turn = await _append_turn(db, session, decision)
    return {"session": _session_dict(session), "turn": _turn_dict(turn)}


async def submit_answer(db: AsyncSession, user: User, session_id, answer: str, nc=None) -> dict:
    session = await _owned_session(db, user, session_id)
    if session.status != "in_progress":
        raise LookupError("session_not_active")
    last_turn = await _latest_turn(db, session.id)
    if last_turn is None or last_turn.answer is not None:
        raise LookupError("no_open_question")
    last_turn.answer = answer
    last_turn.answered_at = datetime.now(UTC)
    last_turn.assisted = bool(last_turn.assistance_level and last_turn.assistance_level > 0)
    await db.commit()

    track_brief = await get_track_with_brief(db, user, session.track_id)
    decision = await _decide(db, session, track_brief["brief"]["content"], last_answer=answer)

    # Persist the evaluation on the answered turn so feedback survives refreshes.
    last_turn.evaluation_coverage = decision.evaluation.coverage
    last_turn.evaluation_strengths = decision.evaluation.strengths
    last_turn.evaluation_gaps = decision.evaluation.gaps
    last_turn.evaluation_detail = {
        "expected_answer_explanation": decision.evaluation.expected_answer_explanation,
        "corrected_code": decision.evaluation.corrected_code,
        "time_complexity": decision.evaluation.time_complexity,
        "space_complexity": decision.evaluation.space_complexity,
    }
    last_turn.interviewer_notes = decision.notes_for_report
    await db.commit()

    turns_so_far = await _count_turns(db, session.id)
    if decision.decision == "complete" or turns_so_far >= get_settings().interview_max_turns:
        if await _complete_if_needed(db, session):
            await _dispatch_feedback(session, nc=nc)
        return {"completed": True, "evaluation": decision.evaluation.model_dump()}

    # Avoid creating a second open question if one somehow already exists.
    latest = await _latest_turn(db, session.id)
    if latest is not None and latest.answer is None:
        return {
            "completed": False,
            "evaluation": decision.evaluation.model_dump(),
            "turn": _turn_dict(latest),
        }

    turn = await _append_turn(db, session, decision)
    return {
        "completed": False,
        "evaluation": decision.evaluation.model_dump(),
        "turn": _turn_dict(turn),
    }


async def get_session(db: AsyncSession, user: User, session_id) -> dict | None:
    try:
        session = await _owned_session(db, user, session_id)
    except LookupError:
        return None
    turns = await _turns(db, session.id)
    return {
        "session": _session_dict(session),
        "turns": [_turn_dict_full(t) for t in turns],
    }


async def request_assistance(db: AsyncSession, user: User, session_id) -> dict:
    """Grant the next progressive assistance level for the open Guided question.

    The client cannot choose the level — progression is server-owned.
    """
    session = await _owned_session(db, user, session_id)
    if session.status != "in_progress":
        raise LookupError("session_not_active")
    if session.mode != "guided":
        raise PermissionError("assistance_not_allowed")

    turn = await _latest_turn(db, session.id)
    if turn is None or turn.answer is not None:
        raise LookupError("no_open_question")

    coding = is_coding_question(turn.question, turn.question_area)
    ceiling = max_level_for_question(turn.question, turn.question_area)
    level = next_assistance_level(turn.assistance_level or 0, max_level=ceiling)
    if level is None:
        raise LookupError("assistance_exhausted")

    assist_type = label_for_level(level, coding=coding)
    content = await run_assistance_turn(
        payload={
            "level": level,
            "assistance_type": assist_type,
            "coding": coding,
            "question": turn.question,
            "question_area": turn.question_area,
            "prior_events": turn.assistance_events or [],
        }
    )
    # Enforce backend level/type even if the model drifts.
    event = {
        "assistance_event_id": str(uuid.uuid4()),
        "level": level,
        "assistance_type": assist_type,
        "content": content.content,
        "created_at": datetime.now(UTC).isoformat(),
    }
    events = list(turn.assistance_events or [])
    events.append(event)
    turn.assistance_level = level
    turn.assistance_events = events
    await db.commit()
    await db.refresh(turn)
    return {
        "session_id": str(session.id),
        "turn_index": turn.turn_index,
        "assistance": {
            "assistance_event_id": event["assistance_event_id"],
            "level": level,
            "assistance_type": assist_type,
            "content": event["content"],
        },
        "assistance_level": level,
        "max_level": ceiling,
        "coding": coding,
    }


async def complete_session(db: AsyncSession, user: User, session_id, nc=None) -> dict | None:
    """Manually finish a session and dispatch feedback (idempotent).

    Already-completed sessions return the current state without publishing
    another feedback job. Ownership is enforced via _owned_session.
    """
    try:
        session = await _owned_session(db, user, session_id)
    except LookupError:
        return None
    if await _complete_if_needed(db, session):
        await _dispatch_feedback(session, nc=nc)
    return {"session": _session_dict(session)}


async def _decide(db: AsyncSession, session, brief_content: dict, *, last_answer: str | None):
    turns = await _turns(db, session.id)
    last_question = turns[-1].question if turns else None
    current_area = turns[-1].question_area if turns else None
    asked_areas = [t.question_area for t in turns]
    covered_areas = list(dict.fromkeys(asked_areas))  # stable unique
    brief_areas = [
        qa["topic"]
        for qa in brief_content.get("question_areas", [])
        if qa.get("topic")
    ]
    remaining_areas = [topic for topic in brief_areas if topic not in covered_areas]
    max_turns = get_settings().interview_max_turns
    questions_asked = len(turns)
    # After this decision we will append one more turn when not completing,
    # so remaining slots for *new* questions accounts for the open turn already counted.
    questions_remaining = max(0, max_turns - questions_asked)
    difficulty = (
        "foundational"
        if questions_asked < 5
        else "intermediate"
        if questions_asked < 10
        else "advanced"
    )
    diversity = (
        "Ask a new question on a distinct learning objective within this track. "
        "Do not restate or paraphrase any asked_questions entry, and do not re-test "
        "the same concepts (e.g. array definition + contiguous storage + static vs "
        "dynamic) under different wording."
    )
    payload = {
        "mode": session.mode,
        "brief": brief_content,
        "transcript": [
            {
                "area": t.question_area,
                "question": t.question,
                "answer": t.answer,
                "assisted": bool(t.assisted),
                "assistance_level": t.assistance_level or 0,
            }
            for t in turns
        ],
        "last_question": last_question,
        "last_answer": last_answer,
        "turns_in_current_area": sum(1 for t in turns if t.question_area == current_area),
        "remaining_areas": remaining_areas,
        "covered_areas": covered_areas,
        "questions_asked": questions_asked,
        "questions_remaining": questions_remaining,
        "max_turns": max_turns,
        "difficulty_target": difficulty,
        # Persistent asked list (survives refresh because turns are in Postgres).
        "asked_questions": [t.question for t in turns],
        "diversity_instruction": diversity,
    }
    # Soft plan slot for this turn (legacy sessions with NULL plan skip this).
    raw_plan = getattr(session, "question_plan", None)
    plan = raw_plan if isinstance(raw_plan, list) else None
    if plan and 0 <= questions_asked < len(plan):
        slot = plan[questions_asked]
        if isinstance(slot, dict):
            payload["question_plan_slot"] = slot
            objective = slot.get("objective", "")
            payload["diversity_instruction"] = (
                f"{diversity} Ask about this objective: {objective}."
            )
    result = await _graph().ainvoke({"payload": payload})
    decision = TurnDecision.model_validate(result["decision"])
    # Defense in depth: never persist a duplicate even if the agent slipped through.
    from app.agents.interviewer import decision_violation, force_unique_decision

    if decision.decision != "complete" and decision_violation(decision, payload):
        decision = force_unique_decision(decision, payload)
    return decision


async def _append_turn(db: AsyncSession, session, decision: TurnDecision) -> SessionTurn:
    index = (await _count_turns(db, session.id)) + 1
    turn = SessionTurn(
        session_id=session.id,
        turn_index=index,
        question_area=decision.question_area,
        question=decision.next_question,
    )
    db.add(turn)
    await db.commit()
    await db.refresh(turn)
    return turn


async def _owned_session(db: AsyncSession, user: User, session_id) -> InterviewSession:
    s = await db.get(InterviewSession, session_id)
    if s is None or s.user_id != user.id:
        raise LookupError("session_not_found")
    return s


async def _turns(db: AsyncSession, session_id) -> list[SessionTurn]:
    result = await db.execute(
        select(SessionTurn)
        .where(SessionTurn.session_id == session_id)
        .order_by(SessionTurn.turn_index)
    )
    return list(result.scalars().all())


async def _count_turns(db: AsyncSession, session_id) -> int:
    result = await db.execute(
        select(func.count()).select_from(SessionTurn).where(SessionTurn.session_id == session_id)
    )
    return int(result.scalar_one())


async def _latest_turn(db: AsyncSession, session_id) -> SessionTurn | None:
    result = await db.execute(
        select(SessionTurn)
        .where(SessionTurn.session_id == session_id)
        .order_by(SessionTurn.turn_index.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _complete_if_needed(db: AsyncSession, session: InterviewSession) -> bool:
    """Mark the session completed. Returns True only on the first transition."""
    if session.status == "completed":
        return False
    session.status = "completed"
    session.completed_at = datetime.now(UTC)
    await db.commit()
    return True


async def _dispatch_feedback(session: InterviewSession, nc=None) -> None:
    """Publish a feedback job for a session that is already committed completed.

    Awaits publish so the job hits JetStream before the HTTP response returns.
    publish_feedback_job never raises; NATS failures are logged and catch-up heals gaps.
    """
    # Snapshot IDs so we never publish a detached/expired ORM identity by mistake.
    session_id = session.id
    track_id = session.track_id
    user_id = session.user_id
    await publish_feedback_job(session_id, track_id, user_id, nc=nc)


def _session_dict(s: InterviewSession) -> dict:
    return {
        "id": str(s.id),
        "track_id": str(s.track_id),
        "mode": s.mode,
        "status": s.status,
        "max_turns": get_settings().interview_max_turns,
    }


def _turn_dict(t: SessionTurn) -> dict:
    return {
        "turn_index": t.turn_index,
        "question_area": t.question_area,
        "question": t.question,
    }


def _turn_dict_full(t: SessionTurn) -> dict:
    d = _turn_dict(t)
    d["answer"] = t.answer
    d["assisted"] = bool(t.assisted)
    d["assistance_level"] = t.assistance_level or 0
    if t.assistance_events:
        d["assistance_events"] = t.assistance_events
    if t.evaluation_coverage is not None:
        detail = t.evaluation_detail or {}
        d["evaluation"] = {
            "coverage": t.evaluation_coverage,
            "strengths": t.evaluation_strengths or [],
            "gaps": t.evaluation_gaps or [],
            "expected_answer_explanation": detail.get("expected_answer_explanation", ""),
            "corrected_code": detail.get("corrected_code", ""),
            "time_complexity": detail.get("time_complexity", ""),
            "space_complexity": detail.get("space_complexity", ""),
        }
    return d
