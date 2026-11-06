import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents.assistance import (
    generate_assistance,
    is_coding_question,
    label_for_level,
    max_level_for_question,
    next_assistance_level,
)
from app.agents.interviewer import TurnDecision, build_interviewer_graph
from app.agents.question_dedupe import concept_fingerprint, is_duplicate_question
from app.agents.question_plan import build_question_plan, opening_areas_to_avoid
from app.agents.question_quality import (
    active_profile,
    is_programming_brief,
    practice_label_for,
    public_question_meta,
    score_mcq,
    score_numeric,
)
from app.agents.session_pool import needs_pool_topup
from app.agents.track_creator import extend_question_pool
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.sqlalchemy import SessionFactory
from app.gateway.llm import llm_model_used
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.services.events import publish_feedback_job
from app.services.progression_policy import VALID_MODES, guided_unlocked
from app.services.track_service import get_track_with_brief

log = get_logger(__name__)


def _unseen_bank_count(bank: list, history: list[str]) -> int:
    count = 0
    for entry in bank:
        text = entry.get("question") if isinstance(entry, dict) else ""
        if text and not is_duplicate_question(text, history):
            count += 1
    return count


_HISTORY_CAP = 80


def _fingerprint(text: str) -> list[str]:
    return sorted(concept_fingerprint(text))


async def _track_history(db, user_id, track_id, exclude_session_id=None) -> list[dict]:
    """Questions already asked on this track, oldest first. Any session status counts.

    Every session's opening question is kept. Other turns are capped so a long
    track does not send its whole history to the planner.
    """
    try:
        stmt = (
            select(
                InterviewSession.id,
                SessionTurn.turn_index,
                SessionTurn.question,
                SessionTurn.question_area,
            )
            .join(InterviewSession, SessionTurn.session_id == InterviewSession.id)
            .where(
                InterviewSession.track_id == track_id,
                InterviewSession.user_id == user_id,
            )
            .order_by(SessionTurn.asked_at.asc(), SessionTurn.turn_index.asc())
        )
        if exclude_session_id is not None:
            stmt = stmt.where(InterviewSession.id != exclude_session_id)
        result = await db.execute(stmt)
    except Exception:
        return []
    rows = [
        {
            "session_id": str(session_id),
            "turn_index": turn_index,
            "question": question,
            "area": area or "",
            "fingerprint": _fingerprint(question),
        }
        for session_id, turn_index, question, area in result.all()
        if question
    ]
    openings = [row for row in rows if row["turn_index"] == 1]
    others = [row for row in rows if row["turn_index"] != 1][-_HISTORY_CAP:]
    kept = {id(row) for row in openings + others}
    return [row for row in rows if id(row) in kept]


def _maybe_topup(brief: dict, history: list[dict], track_id) -> None:
    if not isinstance(brief, dict) or not brief.get("pool"):
        return
    unseen = _unseen_bank_count(
        brief.get("question_bank") or [], [row["question"] for row in history]
    )
    if not needs_pool_topup(unseen, get_settings().interview_max_turns):
        return
    try:
        asyncio.get_running_loop().create_task(_run_pool_topup(track_id))
    except RuntimeError:
        return


async def _run_pool_topup(track_id) -> None:
    try:
        async with SessionFactory() as db:
            track = await db.get(Track, track_id)
            if track is None:
                return
            result = await db.execute(
                select(InterviewBrief)
                .where(InterviewBrief.track_id == track_id)
                .order_by(InterviewBrief.version.desc())
                .limit(1)
            )
            brief = result.scalar_one_or_none()
            content = brief.content if brief is not None else None
            if not isinstance(content, dict) or not content.get("pool"):
                return
            rows = await extend_question_pool(
                brief=content,
                objective={"subject": track.subject, "track_type": track.track_type},
            )
            if not rows:
                return
            updated = dict(content)
            updated["question_bank"] = list(content.get("question_bank") or []) + rows
            brief.content = updated
            flag_modified(brief, "content")
            await db.commit()
    except Exception as exc:
        log.warning("pool_topup_failed", error=str(exc))


async def run_interviewer_turn(**kwargs):
    from app.agents.interviewer import run_interviewer_turn as _run

    return await _run(**kwargs)


async def run_assistance_turn(**kwargs):
    return await generate_assistance(**kwargs)


def _graph():
    return build_interviewer_graph(turn_runner=run_interviewer_turn)


def build_covered_so_far(
    turns: list,
    *,
    plan: list | None,
    questions_asked: int,
) -> dict:
    """Compact session memory for the interviewer (no new tables)."""
    covered_objectives: list[str] = []
    seen: set[str] = set()
    if isinstance(plan, list):
        for i, slot in enumerate(plan):
            if i >= questions_asked or not isinstance(slot, dict):
                break
            obj = (slot.get("objective") or slot.get("topic") or "").strip()
            if obj and obj.lower() not in seen:
                seen.add(obj.lower())
                covered_objectives.append(obj)
    for t in turns:
        area = (getattr(t, "question_area", None) or "").strip()
        if area and area.lower() not in seen:
            seen.add(area.lower())
            covered_objectives.append(area)

    next_planned = None
    if isinstance(plan, list) and 0 <= questions_asked < len(plan):
        slot = plan[questions_asked]
        if isinstance(slot, dict):
            next_planned = {
                "topic": slot.get("topic") or "",
                "objective": slot.get("objective") or "",
                "difficulty": slot.get("difficulty") or "intermediate",
                "format": slot.get("format") or "conceptual",
            }

    weak_areas: list[dict] = []
    for t in turns:
        cov = (getattr(t, "evaluation_coverage", None) or "").lower()
        if cov in ("none", "partial") and getattr(t, "answer", None):
            weak_areas.append(
                {
                    "area": t.question_area,
                    "coverage": cov,
                    "question": (t.question or "")[:160],
                }
            )

    return {
        "covered_objectives": covered_objectives,
        "next_planned_objective": next_planned,
        "weak_areas": weak_areas[:8],
    }


async def start_session(
    db: AsyncSession, user: User, track_id, mode: str = "strict", duration_minutes: int = 60
) -> dict:
    track_brief = await get_track_with_brief(db, user, track_id)
    if track_brief is None:
        raise LookupError("track_not_found")
    if track_brief["track"].get("archived"):
        raise PermissionError("track_archived")
    if track_brief["brief"] is None:
        raise LookupError("brief_not_found")

    mode = (mode or "strict").lower()
    duration_minutes = max(15, min(int(duration_minutes), 240))
    if mode not in VALID_MODES:
        raise ValueError("invalid_mode")
    if mode == "guided" and not await guided_unlocked(db, track_id):
        raise PermissionError("guided_locked")

    brief_content = track_brief["brief"]["content"]
    history = await _track_history(db, user.id, track_id)
    session_id = uuid.uuid4()
    brief_areas = [
        qa.get("topic")
        for qa in (brief_content.get("question_areas") or [])
        if isinstance(qa, dict) and qa.get("topic")
    ]
    plan_brief = {
        **brief_content,
        "plan_seed": str(session_id),
        "prior_areas": list(dict.fromkeys(row["area"] for row in history if row.get("area"))),
        "prior_questions": [row["question"][:160] for row in history][-40:],
        "avoid_areas": opening_areas_to_avoid(
            brief_areas, [row["area"] for row in history if row.get("turn_index") == 1]
        ),
    }
    plan = await build_question_plan(plan_brief, get_settings().interview_max_turns)
    session = InterviewSession(
        id=session_id,
        track_id=track_id,
        user_id=user.id,
        mode=mode,
        duration_minutes=duration_minutes,
        question_plan=plan,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    decision = await _decide(db, session, brief_content, last_answer=None)
    turn = await _append_turn(db, session, decision)
    _maybe_topup(brief_content, history, track_id)
    return {
        "session": _session_dict(session, practice_label=practice_label_for(brief_content)),
        "turn": _turn_dict(turn),
    }


async def submit_answer(db: AsyncSession, user: User, session_id, answer: str, nc=None) -> dict:
    session = await _owned_session(db, user, session_id)
    if session.status != "in_progress":
        raise LookupError("session_not_active")
    # Deadline already passed: finish through the same path as manual complete,
    # and do not store the late answer.
    if _minutes_remaining(session) <= 0:
        await _finish(db, session, nc=nc)
        raise LookupError("deadline_passed")
    last_turn = await _latest_turn(db, session.id)
    if last_turn is None:
        raise LookupError("no_open_question")
    if last_turn.answer is None:
        last_turn.answer = answer
        last_turn.answered_at = datetime.now(UTC)
        last_turn.assisted = bool(last_turn.assistance_level and last_turn.assistance_level > 0)
        await db.commit()
    elif (
        (last_turn.answer or "").strip() == answer.strip()
        and last_turn.evaluation_coverage is None
    ):
        # Quota/503 left the answer saved and the turn unevaluated. Retry
        # scores this same turn instead of opening another one.
        pass
    else:
        raise LookupError("no_open_question")

    track_brief = await get_track_with_brief(db, user, session.track_id)
    decision = await _decide(db, session, track_brief["brief"]["content"], last_answer=answer)
    if (last_turn.question_type or "") == "mcq":
        stored = (
            last_turn.evaluation_detail if isinstance(last_turn.evaluation_detail, dict) else {}
        )
        question_meta = stored.get("question_meta") if isinstance(stored, dict) else {}
        correct = question_meta.get("correct_index") if isinstance(question_meta, dict) else None
        coverage, strengths, gaps = score_mcq(answer, correct)
        decision = decision.model_copy(
            update={
                "evaluation": decision.evaluation.model_copy(
                    update={
                        "coverage": coverage,
                        "strengths": strengths,
                        "gaps": gaps,
                        "expected_answer_explanation": "",
                    }
                )
            }
        )
    elif (last_turn.question_type or "") == "numeric":
        stored = (
            last_turn.evaluation_detail if isinstance(last_turn.evaluation_detail, dict) else {}
        )
        question_meta = stored.get("question_meta") if isinstance(stored, dict) else {}
        question_meta = question_meta if isinstance(question_meta, dict) else {}
        coverage, strengths, gaps = score_numeric(
            answer,
            question_meta.get("expected_value"),
            question_meta.get("tolerance"),
            str(question_meta.get("unit") or ""),
        )
        decision = decision.model_copy(
            update={
                "evaluation": decision.evaluation.model_copy(
                    update={
                        "coverage": coverage,
                        "strengths": strengths,
                        "gaps": gaps,
                        "expected_answer_explanation": "",
                    }
                )
            }
        )

    # M9.2: time is the primary governor — hard-complete at the deadline.
    time_up = _minutes_remaining(session) <= 0

    # Persist the evaluation on the answered turn so feedback survives refreshes.
    last_turn.evaluation_coverage = decision.evaluation.coverage
    last_turn.evaluation_strengths = decision.evaluation.strengths
    last_turn.evaluation_gaps = decision.evaluation.gaps
    detail = {
        "expected_answer_explanation": decision.evaluation.expected_answer_explanation,
        "corrected_code": decision.evaluation.corrected_code,
        "time_complexity": decision.evaluation.time_complexity,
        "space_complexity": decision.evaluation.space_complexity,
        "rubric_version": getattr(decision, "rubric_version", None) or "v1",
        "evaluator_checks": list(getattr(decision, "evaluator_checks", None) or []),
    }
    # Coding answers are reviewed statically — never executed in this product yet.
    prior = last_turn.evaluation_detail if isinstance(last_turn.evaluation_detail, dict) else {}
    if isinstance(prior, dict) and prior.get("question_meta"):
        detail["question_meta"] = prior["question_meta"]
    if (last_turn.question_type or "").lower() == "coding":
        detail["executed"] = False
    used_model = getattr(decision, "model", None) or llm_model_used.get()
    if used_model:
        detail["model"] = used_model
    last_turn.evaluation_detail = detail
    last_turn.interviewer_notes = decision.notes_for_report
    await db.commit()

    turns_so_far = await _count_turns(db, session.id)
    if (
        decision.decision == "complete"
        or time_up
        or turns_so_far >= get_settings().interview_max_turns
    ):
        await _finish(db, session, nc=nc)
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


async def get_open_session(db: AsyncSession, user: User, track_id) -> dict | None:
    track_brief = await get_track_with_brief(db, user, track_id)
    if track_brief is None:
        return None
    result = await db.execute(
        select(InterviewSession)
        .where(
            InterviewSession.track_id == track_id,
            InterviewSession.user_id == user.id,
            InterviewSession.status == "in_progress",
        )
        .order_by(InterviewSession.created_at.desc())
    )
    session = result.scalars().first()
    if session is None:
        return {"session": None}
    turns = await _turns(db, session.id)
    answered = sum(1 for turn in turns if turn.answer is not None)
    question_index = (
        turns[-1].turn_index if turns and turns[-1].answer is None else answered + 1
    )
    created = getattr(session, "created_at", None)
    return {
        "session": {
            "id": str(session.id),
            "mode": session.mode,
            "status": session.status,
            "question_index": question_index,
            "max_turns": get_settings().interview_max_turns,
            "answered_count": answered,
            "created_at": created.isoformat() if created is not None else None,
            "duration_minutes": int(getattr(session, "duration_minutes", None) or 60),
        }
    }


async def get_session(db: AsyncSession, user: User, session_id) -> dict | None:
    try:
        session = await _owned_session(db, user, session_id)
    except LookupError:
        return None
    turns = await _turns(db, session.id)
    track_brief = await get_track_with_brief(db, user, session.track_id)
    brief_content = ((track_brief or {}).get("brief") or {}).get("content") or {}
    return {
        "session": _session_dict(session, practice_label=practice_label_for(brief_content)),
        "turns": [
            _turn_dict_full(t, reveal=session.mode == "guided" and t.answer is not None)
            for t in turns
        ],
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
    await _finish(db, session, nc=nc)
    return {"session": _session_dict(session)}


async def _decide(db: AsyncSession, session, brief_content: dict, *, last_answer: str | None):
    turns = await _turns(db, session.id)
    last_question = turns[-1].question if turns else None
    current_area = turns[-1].question_area if turns else None
    asked_areas = [t.question_area for t in turns]
    covered_areas = list(dict.fromkeys(asked_areas))  # stable unique
    brief_areas = [qa["topic"] for qa in brief_content.get("question_areas", []) if qa.get("topic")]
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
    raw_plan = getattr(session, "question_plan", None)
    plan = raw_plan if isinstance(raw_plan, list) else None
    covered_so_far = build_covered_so_far(turns, plan=plan, questions_asked=questions_asked)

    duration = int(getattr(session, "duration_minutes", None) or 60)
    # Tests may pass a lightweight namespace without created_at / duration.
    try:
        minutes_remaining = round(max(0.0, _minutes_remaining(session)), 1)
        minutes_elapsed = round(duration - minutes_remaining, 1)
    except Exception:
        minutes_remaining = float(duration)
        minutes_elapsed = 0.0
    history: list[dict] = []
    owner_id = getattr(session, "user_id", None)
    owner_track = getattr(session, "track_id", None)
    if owner_id and owner_track:
        history = await _track_history(
            db, owner_id, owner_track, exclude_session_id=getattr(session, "id", None)
        )
    prior_texts = [row["question"] for row in history]
    prior_areas = list(dict.fromkeys(row["area"] for row in history if row.get("area")))
    avoid_areas = (
        []
        if turns
        else opening_areas_to_avoid(
            brief_areas,
            [row["area"] for row in history if row.get("turn_index") == 1 and row.get("area")],
        )
    )
    if avoid_areas:
        diversity += (
            " The opening question must use an area other than: " + ", ".join(avoid_areas) + "."
        )
    payload = {
        "mode": session.mode,
        "meta": {
            # getattr: test doubles may use lightweight namespaces (M11).
            "user_id": str(getattr(session, "user_id", "") or ""),
            "track_id": str(getattr(session, "track_id", "") or ""),
            "session_id": str(getattr(session, "id", "") or ""),
        },
        "duration_minutes": duration,
        "minutes_elapsed": minutes_elapsed,
        "minutes_remaining": minutes_remaining,
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
        "open_question_type": getattr(turns[-1], "question_type", None) if turns else None,
        "turns_in_current_area": sum(1 for t in turns if t.question_area == current_area),
        "remaining_areas": remaining_areas,
        "covered_areas": covered_areas,
        "questions_asked": questions_asked,
        "questions_remaining": questions_remaining,
        "max_turns": max_turns,
        "difficulty_target": difficulty,
        # Persistent asked list (survives refresh because turns are in Postgres).
        "asked_questions": [t.question for t in turns],
        "prior_track_questions": prior_texts,
        "prior_areas": prior_areas,
        "prior_fingerprints": [row["fingerprint"] for row in history],
        "avoid_areas": avoid_areas,
        # M9: validated question bank — only UNUSED entries are exposed, so the
        # interviewer can use them verbatim without tripping duplicate checks.
        "question_bank": [
            q
            for q in brief_content.get("question_bank", [])
            if q.get("question") and q["question"] not in {t.question for t in turns}
        ],
        "covered_so_far": covered_so_far,
        "memory_instruction": (
            "Use covered_so_far: avoid repeating covered_objectives; prefer "
            "next_planned_objective when present; you may revisit ONE weak_areas "
            "entry with a DIFFERENT question (never a rephrase of asked_questions)."
        ),
        "diversity_instruction": diversity,
        "programming_track": is_programming_brief(brief_content),
    }
    profile = active_profile(brief_content)
    if profile:
        payload["domain_profile"] = {
            "category": profile["category"],
            "uses_code": profile["uses_code"],
            "uses_math": profile["uses_math"],
            "risk_level": profile["risk_level"],
            "style_hint": profile["style_hint"],
            "allowed_types": profile["allowed_types"],
        }
        payload["allowed_types"] = profile["allowed_types"]
        payload["programming_track"] = profile["uses_code"]
    if turns:
        stored = turns[-1].evaluation_detail
        detail = stored if isinstance(stored, dict) else {}
        question_meta = detail.get("question_meta") if isinstance(detail, dict) else {}
        if isinstance(question_meta, dict) and question_meta.get("key_points"):
            payload["key_points"] = list(question_meta["key_points"])
    if covered_so_far.get("next_planned_objective"):
        slot = covered_so_far["next_planned_objective"]
        payload["question_plan_slot"] = slot
        payload["preferred_format"] = slot.get("format") or "conceptual"
        payload["diversity_instruction"] = (
            f"{diversity} Ask about this objective: {slot.get('objective', '')}."
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
    meta: dict = {}
    if decision.objective:
        meta["objective"] = decision.objective
    if decision.question_type == "mcq" and decision.options:
        meta["options"] = list(decision.options)
        meta["correct_index"] = decision.correct_index
        meta["explanation"] = decision.option_explanation
    if decision.question_type == "code_read" and decision.code_snippet:
        meta["code_snippet"] = decision.code_snippet
    if decision.question_type == "case_study" and decision.scenario:
        meta["scenario"] = decision.scenario
    if decision.key_points:
        meta["key_points"] = list(decision.key_points)
    if decision.question_type == "numeric":
        meta["expected_value"] = decision.expected_value
        meta["unit"] = decision.unit
        meta["tolerance"] = decision.tolerance
        if decision.option_explanation:
            meta["explanation"] = decision.option_explanation
    turn = SessionTurn(
        session_id=session.id,
        turn_index=index,
        question_area=decision.question_area,
        question=decision.next_question,
        question_type=decision.question_type,
        evaluation_detail={"question_meta": meta} if meta else None,
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


async def _finish(db: AsyncSession, session: InterviewSession, nc=None) -> bool:
    """Complete the session and publish one feedback job.

    Shared by manual finish and time expiry. A second caller sees the row
    already completed and does not publish again.
    """
    if await _complete_if_needed(db, session):
        await _dispatch_feedback(session, nc=nc)
        return True
    return False


async def _complete_if_needed(db: AsyncSession, session: InterviewSession) -> bool:
    """Mark the session completed. Returns True only on the first transition.

    The UPDATE is conditional so two overlapping finish calls (expiry and
    the Finish button) cannot both win.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == session.id,
            InterviewSession.status != "completed",
        )
        .values(status="completed", completed_at=now)
    )
    won = result.rowcount == 1
    await db.commit()
    await db.refresh(session)
    return won


def _minutes_remaining(session: InterviewSession) -> float:
    duration = int(getattr(session, "duration_minutes", None) or 60)
    created = getattr(session, "created_at", None)
    if created is None:
        return float(duration)
    elapsed = (datetime.now(UTC) - created).total_seconds() / 60
    return duration - elapsed


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


def _session_dict(s: InterviewSession, *, practice_label: str = "") -> dict:
    body = {
        "id": str(s.id),
        "track_id": str(s.track_id),
        "mode": s.mode,
        "status": s.status,
        "max_turns": get_settings().interview_max_turns,
        "duration_minutes": s.duration_minutes,
        "created_at": s.created_at.isoformat(),
    }
    if practice_label:
        body["practice_label"] = practice_label
    return body


def _turn_dict(t: SessionTurn, *, reveal: bool = False) -> dict:
    body = {
        "turn_index": t.turn_index,
        "question_area": t.question_area,
        "question": t.question,
        "question_type": t.question_type,
    }
    body.update(public_question_meta(t.evaluation_detail, reveal=reveal))
    return body


def _turn_dict_full(t: SessionTurn, *, reveal: bool = False) -> dict:
    d = _turn_dict(t, reveal=reveal)
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
