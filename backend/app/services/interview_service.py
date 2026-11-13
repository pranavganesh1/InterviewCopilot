import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents import question_plan
from app.agents.assistance import (
    generate_assistance,
    is_coding_question,
    label_for_level,
    max_level_for_question,
    next_assistance_level,
)
from app.agents.interviewer import TurnDecision, build_interviewer_graph
from app.agents.question_dedupe import fingerprint_tuple, is_duplicate_question
from app.agents.question_plan import opening_areas_to_avoid
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
from app.services import probe as probe_service
from app.services import weakness as weakness_service
from app.services.events import publish_feedback_job
from app.services.progression_policy import VALID_MODES, guided_unlocked
from app.services.track_service import get_track_with_brief
from app.services.vault_service import list_items

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
    return list(fingerprint_tuple(text))


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


async def _track_answered_turns(db: AsyncSession, user_id, track_id) -> tuple[list, list]:
    """Answered turns and session ids (oldest first) for weakness aggregation."""
    rows = (
        await db.execute(
            select(SessionTurn, InterviewSession.id)
            .join(InterviewSession, SessionTurn.session_id == InterviewSession.id)
            .where(
                InterviewSession.track_id == track_id,
                InterviewSession.user_id == user_id,
                SessionTurn.answer.is_not(None),
            )
            .order_by(InterviewSession.created_at.asc(), SessionTurn.turn_index.asc())
        )
    ).all()
    turns = []
    session_ids: list = []
    seen: set = set()
    for turn, sid in rows:
        turns.append(turn)
        key = str(sid)
        if key not in seen:
            seen.add(key)
            session_ids.append(sid)
    return turns, session_ids


def _track_start_lock_key(user_id, track_id) -> int:
    """Stable positive int64 for pg_advisory_xact_lock (user+track)."""
    return int(uuid.UUID(str(user_id)).int ^ uuid.UUID(str(track_id)).int) & ((1 << 63) - 1)


def _session_options_match(
    session: InterviewSession,
    *,
    mode: str,
    duration_minutes: int,
    use_resume: bool,
    focus_weak: bool,
    persona_id: str | None,
) -> bool:
    if session.mode != mode:
        return False
    if int(getattr(session, "duration_minutes", None) or 60) != int(duration_minutes):
        return False
    opts = probe_service.session_opts_from_plan(getattr(session, "question_plan", None))
    return (
        bool(opts.get("use_resume")) == bool(use_resume)
        and bool(opts.get("focus_weak")) == bool(focus_weak)
        and (opts.get("persona_id") or "balanced") == (persona_id or "balanced")
    )


async def _answered_turn_count(db: AsyncSession, session_id) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(SessionTurn)
        .where(SessionTurn.session_id == session_id, SessionTurn.answer.is_not(None))
    )
    return int(result.scalar_one())


async def _lock_track_starts(db: AsyncSession, user_id, track_id) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": _track_start_lock_key(user_id, track_id)},
    )


async def _list_open_sessions_for_track(
    db: AsyncSession, user_id, track_id, *, for_update: bool = False
) -> list[InterviewSession]:
    stmt = (
        select(InterviewSession)
        .where(
            InterviewSession.track_id == track_id,
            InterviewSession.user_id == user_id,
            InterviewSession.status == "in_progress",
        )
        .order_by(InterviewSession.created_at.desc())
    )
    if for_update:
        stmt = stmt.with_for_update()
    return list((await db.execute(stmt)).scalars().all())


def _opening_from_question_bank(
    brief_content: dict,
    *,
    plan: list | None,
    session_id,
    mode: str,
    history: list[dict],
) -> "TurnDecision | None":
    """Serve Q1 from the validated bank when possible — no LLM round-trip."""
    from app.agents.interviewer import TurnDecision
    from app.agents.session_pool import pick_pool_question

    bank = [
        q
        for q in (brief_content.get("question_bank") or [])
        if isinstance(q, dict) and (q.get("question") or "").strip()
    ]
    if not bank:
        return None
    slot = plan[0] if isinstance(plan, list) and plan and isinstance(plan[0], dict) else None
    prior_texts = [row["question"] for row in history if row.get("question")]
    avoid = opening_areas_to_avoid(
        [qa.get("topic") for qa in (brief_content.get("question_areas") or []) if qa.get("topic")],
        [row["area"] for row in history if row.get("turn_index") == 1 and row.get("area")],
    )
    chosen = pick_pool_question(
        bank,
        seed=str(session_id),
        slot=slot,
        asked=[],
        history=prior_texts,
        covered_areas=[],
        mode=mode,
        fingerprints=[
            tuple(fp)
            for row in history
            if (fp := row.get("fingerprint")) and len(fp) >= 4
        ],
        avoid_areas=avoid,
        reuse=False,
    )
    if not chosen:
        return None
    area = (
        (chosen.get("area") or "").strip()
        or (slot or {}).get("topic")
        or "Core concepts"
    )
    qtype = (chosen.get("type") or chosen.get("question_type") or "conceptual").strip()
    if qtype not in (
        "coding",
        "conceptual",
        "behavioral",
        "mcq",
        "code_read",
        "case_study",
        "numeric",
    ):
        qtype = "conceptual"
    return TurnDecision(
        evaluation={"coverage": "none", "strengths": [], "gaps": []},
        decision="next_area",
        next_question=(chosen.get("question") or "").strip(),
        question_area=str(area)[:255],
        question_type=qtype,  # type: ignore[arg-type]
        objective=str((slot or {}).get("objective") or "")[:500],
        notes_for_report="question_bank",
    )


async def start_session(
    db: AsyncSession,
    user: User,
    track_id,
    mode: str = "strict",
    duration_minutes: int = 60,
    use_resume: bool = False,
    focus_weak: bool = False,
    persona_id: str | None = None,
    claim_seeds: list | None = None,
    mongo_db: object = None,
    request_id: str | None = None,
) -> dict:
    from app.agents.persona import bias_plan_for_persona, normalize_persona_id

    started = time.monotonic()
    rid = (request_id or "")[:64] or None
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
    persona_id = normalize_persona_id(persona_id)

    brief_content = track_brief["brief"]["content"]
    practice = practice_label_for(brief_content)

    # Serialize starts per user+track so double-clicks cannot create twins.
    await _lock_track_starts(db, user.id, track_id)
    open_rows = await _list_open_sessions_for_track(db, user.id, track_id, for_update=True)
    empty_opens: list[InterviewSession] = []
    answered_opens: list[InterviewSession] = []
    expired_for_feedback: list[InterviewSession] = []
    closed_expired = False
    now = datetime.now(UTC)
    for row in open_rows:
        # Never reuse / block on a session whose timer already expired.
        # Keep the advisory xact lock: mutate in-place; commit with this start.
        if _session_timed_out(row):
            answered = await _answered_turn_count(db, row.id)
            if answered == 0:
                row.status = "aborted"
                row.completed_at = now
                closed_expired = True
                log.info(
                    "interview_expired_empty_aborted",
                    session_id=str(row.id),
                    track_id=str(track_id),
                )
            else:
                row.status = "completed"
                row.completed_at = now
                closed_expired = True
                expired_for_feedback.append(row)
                log.info(
                    "interview_expired_answered_finished",
                    session_id=str(row.id),
                    track_id=str(track_id),
                )
            continue
        if await _answered_turn_count(db, row.id) == 0:
            empty_opens.append(row)
        else:
            answered_opens.append(row)

    if answered_opens:
        # Persist any expired closures before refusing a second active session.
        if closed_expired:
            await db.commit()
            for done in expired_for_feedback:
                await _dispatch_feedback(done)
        # Resume/finish must be explicit; do not open a second in-progress session.
        raise PermissionError("open_session_in_progress")

    if empty_opens:
        matching = [
            row
            for row in empty_opens
            if _session_options_match(
                row,
                mode=mode,
                duration_minutes=duration_minutes,
                use_resume=use_resume,
                focus_weak=focus_weak,
                persona_id=persona_id,
            )
        ]
        if matching:
            # Active empty with same options — safe dedupe / refresh (keep timer).
            chosen = matching[0]
            turn = await _latest_turn(db, chosen.id)
            if turn is None:
                # Rare orphan (in_progress, no turns): mint Q1 instead of creating a twin.
                try:
                    hist = await _track_history(
                        db, user.id, track_id, exclude_session_id=chosen.id
                    )
                    decision = _opening_from_question_bank(
                        brief_content,
                        plan=getattr(chosen, "question_plan", None),
                        session_id=chosen.id,
                        mode=mode,
                        history=hist,
                    )
                    if decision is None:
                        decision = await _decide(
                            db,
                            chosen,
                            brief_content,
                            last_answer=None,
                            mongo_db=mongo_db,
                        )
                except Exception:
                    chosen.status = "aborted"
                    chosen.completed_at = datetime.now(UTC)
                    await db.commit()
                    raise
                turn = await _append_turn(db, chosen, decision)
            await db.commit()
            for done in expired_for_feedback:
                await _dispatch_feedback(done)
            return {
                "session": _session_dict(chosen, practice_label=practice),
                "turn": _turn_dict(turn),
            }
        # Different mode/duration/persona: close stale empties, then create fresh.
        for row in empty_opens:
            row.status = "aborted"
            row.completed_at = now
        # Fall through — new session commit also persists these aborts.

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
    # Resume-based sessions: fold real vault topics into the plan so interviews
    # cover projects/skills/experience from the candidate's background — not a
    # CS-default topic list.
    if use_resume:
        vault_for_plan = probe_service.vault_plan_areas(
            await list_items(db, user.id),
            limit=8,
        )
        if vault_for_plan:
            existing = [
                qa
                for qa in (plan_brief.get("question_areas") or [])
                if isinstance(qa, dict) and qa.get("topic")
            ]
            seen = {(qa.get("topic") or "").strip().lower() for qa in existing}
            merged = list(existing)
            for area in vault_for_plan:
                key = (area.get("topic") or "").strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(area)
            plan_brief["question_areas"] = merged[:12]
    t_plan = time.monotonic()
    # Deterministic plan only at start — avoids a full LLM plan call before Q1.
    plan = await question_plan.build_question_plan(
        plan_brief,
        get_settings().interview_max_turns,
        allow_llm=False,
        duration_minutes=duration_minutes,
    )
    log.info(
        "interview_start_timing",
        stage="question_plan",
        request_id=rid,
        elapsed_ms=int((time.monotonic() - t_plan) * 1000),
        allow_llm=False,
        slots=len(plan),
    )
    answered_turns, session_ids = await _track_answered_turns(db, user.id, track_id)
    weak_summary = weakness_service.aggregate_turns(answered_turns, session_order=session_ids)
    weak_names = weakness_service.weak_concept_names(weak_summary, focus=focus_weak)
    if focus_weak and weak_names:
        # Replace ~30% of slots with weak-concept objectives (new questions later).
        for i, slot in enumerate(plan):
            if not isinstance(slot, dict):
                continue
            if i % 3 == 0:
                concept = weak_names[(i // 3) % len(weak_names)]
                slot = dict(slot)
                slot["topic"] = concept
                slot["objective"] = f"Retest understanding of {concept}"
                plan[i] = slot
    elif weak_names:
        plan = probe_service.bias_plan_for_weaknesses(plan, weak_names)
    plan = bias_plan_for_persona(plan, persona_id)
    seeds = claim_seeds if use_resume else None
    plan = probe_service.attach_session_opts(
        plan,
        use_resume=use_resume,
        focus_weak=focus_weak,
        persona_id=persona_id,
        claim_seeds=seeds,
    )
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
    log.info(
        "interview_start_timing",
        stage="session_persisted",
        request_id=rid,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        session_id=str(session.id),
    )

    # M11 fix: if the first question fails, don't leave a stuck orphan
    # session (in_progress with zero turns). Mark aborted, then re-raise —
    # the user retries cleanly and nothing is stuck on "Preparing…".
    try:
        t_q1 = time.monotonic()
        decision = _opening_from_question_bank(
            brief_content,
            plan=plan,
            session_id=session.id,
            mode=mode,
            history=history,
        )
        q1_path = "question_bank"
        if decision is None:
            q1_path = "llm"
            decision = await _decide(
                db, session, brief_content, last_answer=None, mongo_db=mongo_db
            )
        turn = await _append_turn(db, session, decision)
        log.info(
            "interview_start_timing",
            stage="first_question",
            request_id=rid,
            path=q1_path,
            elapsed_ms=int((time.monotonic() - t_q1) * 1000),
            total_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:
        session.status = "aborted"
        await db.commit()
        log.warning(
            "interview_start_failed",
            request_id=rid,
            cause=type(exc).__name__,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
        raise
    for done in expired_for_feedback:
        await _dispatch_feedback(done)
    _maybe_topup(brief_content, history, track_id)
    log.info(
        "interview_start_timing",
        stage="total",
        request_id=rid,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        path=q1_path,
    )
    return {
        "session": _session_dict(session, practice_label=practice),
        "turn": _turn_dict(turn),
    }


async def submit_answer(
    db: AsyncSession, user: User, session_id, answer: str, nc=None, mongo_db: object = None
) -> dict:
    session = await _owned_session(db, user, session_id)
    if session.status != "in_progress":
        raise LookupError("session_not_active")
    # Deadline already passed: finish through the same path as manual complete,
    # and do not store the late answer.
    if _session_timed_out(session):
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
    elif last_turn.evaluation_coverage is None:
        # Answer was saved but evaluation / next question never finished
        # (timeout, 503, etc.). Allow retry with the same or edited text.
        last_turn.answer = answer
        last_turn.answered_at = datetime.now(UTC)
        last_turn.assisted = bool(last_turn.assistance_level and last_turn.assistance_level > 0)
        await db.commit()
    else:
        raise LookupError("no_open_question")

    track_brief = await get_track_with_brief(db, user, session.track_id)
    decision = await _decide(
        db, session, track_brief["brief"]["content"], last_answer=answer, mongo_db=mongo_db
    )
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
    time_up = _session_timed_out(session)

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


def _open_session_progress(turns: list[SessionTurn]) -> tuple[int, int]:
    answered = sum(1 for turn in turns if turn.answer is not None)
    question_index = turns[-1].turn_index if turns and turns[-1].answer is None else answered + 1
    return answered, question_index


def _open_session_payload(session: InterviewSession, turns: list[SessionTurn]) -> dict:
    answered, question_index = _open_session_progress(turns)
    created = getattr(session, "created_at", None)
    remaining = round(max(0.0, _minutes_remaining(session)), 1)
    return {
        "id": str(session.id),
        "mode": session.mode,
        "status": session.status,
        "question_index": question_index,
        "max_turns": get_settings().interview_max_turns,
        "answered_count": answered,
        "created_at": _as_utc(created).isoformat() if created is not None else None,
        "duration_minutes": int(getattr(session, "duration_minutes", None) or 60),
        "minutes_remaining": remaining,
    }


async def get_open_session(
    db: AsyncSession, user: User, track_id, *, limit: int = 20
) -> dict | None:
    track_brief = await get_track_with_brief(db, user, track_id)
    if track_brief is None:
        return None
    limit = max(1, min(int(limit or 20), 50))
    rows = await _list_open_sessions_for_track(db, user.id, track_id)
    sessions: list[dict] = []
    for session in rows:
        if _session_timed_out(session):
            continue
        turns = await _turns(db, session.id)
        sessions.append(_open_session_payload(session, turns))
        if len(sessions) >= limit:
            break
    return {"session": sessions[0] if sessions else None, "sessions": sessions}


async def list_open_sessions_for_user(
    db: AsyncSession, user: User, *, limit: int | None = None
) -> list[dict]:
    """Unfinished interviews across the owner's non-archived tracks (newest first)."""
    stmt = (
        select(InterviewSession, Track)
        .join(Track, Track.id == InterviewSession.track_id)
        .where(
            InterviewSession.user_id == user.id,
            InterviewSession.status == "in_progress",
            Track.archived_at.is_(None),
        )
        .order_by(InterviewSession.created_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(max(1, min(int(limit), 100)))
    rows = (await db.execute(stmt)).all()
    max_turns = get_settings().interview_max_turns
    items: list[dict] = []
    for session, track in rows:
        if _session_timed_out(session):
            continue
        turns = await _turns(db, session.id)
        answered, question_index = _open_session_progress(turns)
        created = getattr(session, "created_at", None)
        items.append(
            {
                "session_id": str(session.id),
                "track_id": str(track.id),
                "track_subject": track.subject,
                "mode": session.mode,
                "status": session.status,
                "question_index": question_index,
                "max_turns": max_turns,
                "answered_count": answered,
                "created_at": _as_utc(created).isoformat() if created is not None else None,
                "duration_minutes": int(getattr(session, "duration_minutes", None) or 60),
                "minutes_remaining": round(max(0.0, _minutes_remaining(session)), 1),
            }
        )
    return items


async def abort_session(db: AsyncSession, user: User, session_id) -> dict | None:
    """Close one owned in-progress session without deleting rows or scoring."""
    try:
        session = await _owned_session(db, user, session_id)
    except LookupError:
        return None
    if session.status != "in_progress":
        return {"session": _session_dict(session)}
    session.status = "aborted"
    session.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(session)
    return {"session": _session_dict(session)}


async def close_empty_sessions_for_track(db: AsyncSession, user: User, track_id) -> dict:
    """Abort open sessions on this track with 0 answered turns (no feedback job)."""
    track_brief = await get_track_with_brief(db, user, track_id)
    if track_brief is None:
        raise LookupError("track_not_found")
    closed: list[str] = []
    for session in await _list_open_sessions_for_track(db, user.id, track_id):
        if await _answered_turn_count(db, session.id) != 0:
            continue
        session.status = "aborted"
        session.completed_at = datetime.now(UTC)
        closed.append(str(session.id))
    if closed:
        await db.commit()
    return {"closed_count": len(closed), "session_ids": closed}


async def find_empty_sessions_for_cleanup(
    db: AsyncSession, *, older_than_minutes: int = 10
) -> list[InterviewSession]:
    """Open sessions with 0 answers, no feedback report, older than the cutoff."""
    from app.models.feedback import FeedbackReport

    cutoff = datetime.now(UTC) - timedelta(minutes=max(1, int(older_than_minutes)))
    rows = (
        (
            await db.execute(
                select(InterviewSession)
                .outerjoin(FeedbackReport, FeedbackReport.session_id == InterviewSession.id)
                .where(
                    InterviewSession.status == "in_progress",
                    InterviewSession.created_at < cutoff,
                    FeedbackReport.id.is_(None),
                )
                .order_by(InterviewSession.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    eligible: list[InterviewSession] = []
    for session in rows:
        if await _answered_turn_count(db, session.id) == 0:
            eligible.append(session)
    return eligible


async def abort_sessions_by_ids(db: AsyncSession, session_ids: list) -> int:
    """Mark the given sessions aborted (existing close path; never deletes)."""
    if not session_ids:
        return 0
    now = datetime.now(UTC)
    result = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id.in_(session_ids),
            InterviewSession.status == "in_progress",
        )
        .values(status="aborted", completed_at=now)
    )
    await db.commit()
    return int(result.rowcount or 0)


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


async def _decide(
    db: AsyncSession,
    session,
    brief_content: dict,
    *,
    last_answer: str | None,
    mongo_db: object = None,
) -> "TurnDecision":
    turns = await _turns(db, session.id)
    last_question = turns[-1].question if turns else None
    current_area = turns[-1].question_area if turns else None
    asked_areas = [t.question_area for t in turns]
    covered_areas = list(dict.fromkeys(asked_areas))  # stable unique
    brief_areas = [qa["topic"] for qa in brief_content.get("question_areas", []) if qa.get("topic")]
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
    diversity = ""  # static rules live in the system prompts (M11 trim)
    raw_plan = getattr(session, "question_plan", None)
    plan = raw_plan if isinstance(raw_plan, list) else None
    # Prefer subjects from the persisted plan (includes duration enrichment) so
    # progression works even when the brief itself is thin.
    subject_pool = question_plan.plan_topics(plan) or brief_areas
    covered_keys = {a.lower() for a in covered_areas if a}
    remaining_areas = [t for t in subject_pool if t.lower() not in covered_keys]
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
    asked_set = {t.question for t in turns}
    opts = probe_service.session_opts_from_plan(plan)
    payload = {
        "mode": session.mode,
        "persona_id": opts.get("persona_id") or "balanced",
        "meta": {
            # getattr: test doubles may use lightweight namespaces (M11).
            "user_id": str(getattr(session, "user_id", "") or ""),
            "track_id": str(getattr(session, "track_id", "") or ""),
            "session_id": str(getattr(session, "id", "") or ""),
        },
        "duration_minutes": duration,
        "minutes_elapsed": minutes_elapsed,
        "minutes_remaining": minutes_remaining,
        # M11 trim: compact brief — the interviewer needs areas, angle, types
        # and the unused bank; not the student's preparation_plan or long
        # competency descriptions (token weight per turn).
        "brief": {
            "summary": (brief_content.get("summary") or "")[:300],
            "question_areas": [
                {
                    "topic": qa.get("topic", ""),
                    "guidance": (qa.get("guidance") or "")[:100],
                }
                for qa in (brief_content.get("question_areas") or [])
            ],
            "candidate_angle_notes": (brief_content.get("candidate_angle_notes") or "")[:250],
            "domain_profile": brief_content.get("domain_profile") or {},
            "allowed_types": brief_content.get("allowed_types") or [],
            "pool": brief_content.get("pool") or {},
            # Only UNUSED bank entries, question text only (no sketches).
            "question_bank": [
                {"area": q.get("area", ""), "question": q.get("question", "")}
                for q in (brief_content.get("question_bank") or [])
                if q.get("question") and q["question"] not in asked_set
            ],
        },
        "transcript": [
            {
                "area": t.question_area,
                "question": t.question,
                "answer": (t.answer or "")[:400],
                "assisted": bool(t.assisted),
                "assistance_level": t.assistance_level or 0,
            }
            for t in turns
        ],
        "last_question": last_question,
        "last_answer": last_answer,
        "open_question_type": getattr(turns[-1], "question_type", None) if turns else None,
        "turns_in_current_area": sum(1 for t in turns if t.question_area == current_area),
        "current_area": current_area,
        "topic_budget": question_plan.topic_block_size(plan, current_area),
        "remaining_areas": remaining_areas,
        "covered_areas": covered_areas,
        "question_plan": plan,
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
            for q in (brief_content.get("question_bank") or [])
            if q.get("question") and q["question"] not in asked_set
        ],
        "covered_so_far": covered_so_far,
        "memory_instruction": (
            "Use covered_so_far: avoid repeating covered_objectives; prefer "
            "next_planned_objective when present; stay on the planned subject for "
            "about topic_budget questions, then advance to the next planned subject "
            "automatically — do not wait for the candidate to ask for the next topic. "
            "follow_up only for none/partial coverage; never burn the plan on soft "
            "same-concept follow-ups. You may revisit ONE weak_areas entry with a "
            "DIFFERENT question (never a rephrase of asked_questions)."
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
        if isinstance(question_meta, dict) and question_meta.get("probe_context"):
            payload["probe_context"] = str(question_meta["probe_context"])[:160]
            payload["probe_origin"] = question_meta.get("origin")
    if covered_so_far.get("next_planned_objective"):
        slot = covered_so_far["next_planned_objective"]
        payload["question_plan_slot"] = slot
        payload["preferred_format"] = slot.get("format") or "conceptual"
        payload["diversity_instruction"] = (
            f"{diversity} Ask about this objective: {slot.get('objective', '')}."
        )
    vault_items: list[dict] = []
    weak_names: list[str] = []
    if opts.get("use_resume") or opts.get("focus_weak"):
        if opts.get("use_resume"):
            vault_items = probe_service.sanitize_vault_items(await list_items(db, session.user_id))
            if vault_items:
                payload["vault_prompt_block"] = probe_service.vault_prompt_block(vault_items)
        answered_turns, session_ids = await _track_answered_turns(
            db, session.user_id, session.track_id
        )
        weak_summary = weakness_service.aggregate_turns(answered_turns, session_order=session_ids)
        weak_names = weakness_service.weak_concept_names(
            weak_summary, focus=bool(opts.get("focus_weak"))
        )

    result = await _graph().ainvoke({"payload": payload, "mongo_db": mongo_db})
    decision = TurnDecision.model_validate(result["decision"])
    # Defense in depth: never persist a duplicate even if the agent slipped through.
    from app.agents.interviewer import decision_violation, force_unique_decision

    if decision.decision != "complete" and decision_violation(decision, payload):
        decision = force_unique_decision(decision, payload)

    # Opt-in probes replace a plan slot; they never extend the session or
    # overwrite the evaluator's coverage of the answer just given.
    if decision.decision != "complete" and (opts.get("use_resume") or opts.get("focus_weak")):
        probe = probe_service.pick_probe(
            opts=opts,
            vault_items=vault_items,
            weak_concepts=weak_names,
            last_answer=last_answer,
            current_area=current_area or "",
            turns=turns,
            prior_questions=prior_texts,
            mode=session.mode,
            max_turns=max_turns,
            questions_asked=questions_asked,
            questions_remaining=questions_remaining,
            minutes_remaining=minutes_remaining,
        )
        if probe:
            kept = decision.evaluation.model_dump()
            decision = TurnDecision.model_validate({**probe, "evaluation": kept})

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
    # Probe origin is carried on notes_for_report from pick_probe; also accept objective.
    origin = (decision.notes_for_report or "").strip()
    if origin in probe_service.PROBE_ORIGINS:
        meta["origin"] = origin
        meta["probe_context"] = (decision.objective or "")[:160]
        if origin == "answer_probe":
            meta["probe_label"] = "Follow-up on your answer"
        elif origin == "resume_probe":
            title = (decision.objective or decision.question_area or "your project")[:80]
            meta["project_name"] = title
            meta["probe_label"] = f"From your project: {title}"
        elif origin == "weakness_retest":
            meta["probe_label"] = "Weak area re-test"
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


def _as_utc(value: datetime) -> datetime:
    """Normalize DB timestamps so naive/aware values compare safely as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _minutes_remaining(session: InterviewSession) -> float:
    duration = int(getattr(session, "duration_minutes", None) or 60)
    created = getattr(session, "created_at", None)
    if created is None:
        return float(duration)
    elapsed = (datetime.now(UTC) - _as_utc(created)).total_seconds() / 60
    return duration - elapsed


def _session_timed_out(session: InterviewSession) -> bool:
    return _minutes_remaining(session) <= 0


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
    opts = probe_service.session_opts_from_plan(getattr(s, "question_plan", None))
    from app.agents.persona import get_persona

    persona = get_persona(opts.get("persona_id"))
    body = {
        "id": str(s.id),
        "track_id": str(s.track_id),
        "mode": s.mode,
        "status": s.status,
        "max_turns": get_settings().interview_max_turns,
        "duration_minutes": s.duration_minutes,
        "created_at": _as_utc(s.created_at).isoformat() if s.created_at else None,
        "persona_id": persona.id,
        "persona_name": persona.name,
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
