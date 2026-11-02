from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.interviewer import TurnDecision, build_interviewer_graph
from app.core.config import get_settings
from app.models.interview import InterviewSession, SessionTurn
from app.models.user import User
from app.services.track_service import get_track_with_brief


async def run_interviewer_turn(**kwargs):
    from app.agents.interviewer import run_interviewer_turn as _run

    return await _run(**kwargs)


def _graph():
    return build_interviewer_graph(turn_runner=run_interviewer_turn)


async def start_session(db: AsyncSession, user: User, track_id, mode: str = "strict") -> dict:
    track_brief = await get_track_with_brief(db, user, track_id)
    if track_brief is None:
        raise LookupError("track_not_found")
    if track_brief["brief"] is None:
        raise LookupError("brief_not_found")

    session = InterviewSession(track_id=track_id, user_id=user.id, mode=mode)
    db.add(session)
    await db.commit()
    await db.refresh(session)

    decision = await _decide(db, session, track_brief["brief"]["content"], last_answer=None)
    turn = await _append_turn(db, session, decision)
    return {"session": _session_dict(session), "turn": _turn_dict(turn)}


async def submit_answer(db: AsyncSession, user: User, session_id, answer: str) -> dict:
    session = await _owned_session(db, user, session_id)
    last_turn = await _latest_turn(db, session.id)
    if last_turn is None or last_turn.answer is not None:
        raise LookupError("no_open_question")
    last_turn.answer = answer
    last_turn.answered_at = datetime.now(UTC)
    await db.commit()

    track_brief = await get_track_with_brief(db, user, session.track_id)
    decision = await _decide(db, session, track_brief["brief"]["content"], last_answer=answer)

    turns_so_far = await _count_turns(db, session.id)
    if decision.decision == "complete" or turns_so_far >= get_settings().interview_max_turns:
        await _complete(db, session)
        return {"completed": True, "evaluation": decision.evaluation.model_dump()}

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


async def complete_session(db: AsyncSession, user: User, session_id) -> dict | None:
    try:
        session = await _owned_session(db, user, session_id)
    except LookupError:
        return None
    await _complete(db, session)
    return {"session": _session_dict(session)}


async def _decide(db: AsyncSession, session, brief_content: dict, *, last_answer: str | None):
    turns = await _turns(db, session.id)
    last_question = turns[-1].question if turns else None
    current_area = turns[-1].question_area if turns else None
    payload = {
        "brief": brief_content,
        "transcript": [
            {"area": t.question_area, "question": t.question, "answer": t.answer} for t in turns
        ],
        "last_question": last_question,
        "last_answer": last_answer,
        "turns_in_current_area": sum(1 for t in turns if t.question_area == current_area),
        "questions_asked": len(turns),
    }
    result = await _graph().ainvoke({"payload": payload})
    return TurnDecision.model_validate(result["decision"])


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
    return len(await _turns(db, session_id))


async def _latest_turn(db: AsyncSession, session_id) -> SessionTurn | None:
    turns = await _turns(db, session_id)
    return turns[-1] if turns else None


async def _complete(db: AsyncSession, session: InterviewSession) -> None:
    session.status = "completed"
    session.completed_at = datetime.now(UTC)
    await db.commit()


def _session_dict(s: InterviewSession) -> dict:
    return {
        "id": str(s.id),
        "track_id": str(s.track_id),
        "mode": s.mode,
        "status": s.status,
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
    return d
