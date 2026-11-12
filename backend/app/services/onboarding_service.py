import time
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import (
    ExtractedItem,
    OnboardingTurn,
    ack_followup_question,
    build_onboarding_graph,
    classify_duplicate_answer,
    classify_practise_intent,
    compute_profile_gaps,
    derive_phase,
    ensure_nonempty_reply,
    is_ack_only,
    practise_followup_reply,
    recent_duplicate_prompt,
    vault_is_ready,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.gateway.llm import LLMGatewayError
from app.models.user import User
from app.services import conversation_store
from app.services.preparation_goals import (
    GOAL_INTERESTS,
    GOALS_INTRO_MARKER,
    build_resume_goal_options,
    followups_complete,
    goals_followup_reply,
    goals_intro_message,
    infer_candidate_background,
    merge_preferences,
    next_goal_followup,
    preferences_ready,
    project_titles,
    recommend_track_seeds,
    skill_titles,
    summarize_preferences,
)
from app.services.preparation_review import (
    build_review,
    empty_review,
    merge_review_patch,
)
from app.services.vault_service import (
    build_profile_review_message,
    delete_item,
    find_near_duplicates,
    list_items,
    message_looks_like_resume_welcome,
    upsert_extracted_items,
    vault_summary,
)

log = get_logger(__name__)

CONVERSATION_STARTERS: dict[str, dict[str, str]] = {
    "ai_interview": {
        "label": "Start AI Interview",
        "description": "A friendly warm-up using your resume — one question at a time.",
        "message": (
            "I'd like to start an AI interview warm-up based on my resume. "
            "Ask me one introduction question at a time about my background."
        ),
    },
    "explore_projects": {
        "label": "Explore My Projects",
        "description": "Deep-dive a project from your vault with smart follow-ups.",
        "message": (
            "Let's explore my projects from my resume. "
            "Ask about one project at a time using only what's in my vault."
        ),
    },
    "test_skills": {
        "label": "Test My Skills",
        "description": "Pick skills from your profile and practise them conversationally.",
        "message": (
            "I want to explore skills from my resume. "
            "Show me what's on file and ask which ones I want to practise."
        ),
    },
    "career_goal": {
        "label": "Set My Career Goal",
        "description": "Choose roles, placement focus, and interview preparation goals.",
        "message": (
            "Let's set my career goal for interview preparation — "
            "role, internship or full-time, and what I want to practise."
        ),
    },
}


async def run_onboarding_turn(**kwargs):
    """Indirection so tests can patch the agent turn without rebuilding the graph."""
    from app.agents.onboarding import run_onboarding_turn as _run

    return await _run(**kwargs)


def _skill_titles(summary: list[dict]) -> list[str]:
    return skill_titles(summary)


def _project_titles(summary: list[dict]) -> list[str]:
    return project_titles(summary)


def _message_signals_skip(message: str) -> bool:
    text = (message or "").lower()
    return any(
        p in text
        for p in (
            "skip",
            "not sure",
            "don't know",
            "dont know",
            "i'm not sure",
            "im not sure",
            "move on",
            "later",
            "doesn't apply",
            "does not apply",
            "not applicable",
            "n/a",
            "no degree",
            "no project",
            "no experience",
        )
    )


async def _apply_duplicate_decision(
    db: AsyncSession,
    user_id,
    decision: str,
    pair: dict,
) -> str:
    """Mutate vault for merge; keep_both leaves both rows. Returns confirmation text."""
    a_title = str((pair.get("a") or {}).get("title") or "entry")
    b_title = str((pair.get("b") or {}).get("title") or "entry")
    category = str(pair.get("category") or "item")
    if decision == "keep_both":
        return f"Kept both {category} entries — “{a_title}” and “{b_title}”."
    # merge: fold b into a when possible, then remove b
    a_id = (pair.get("a") or {}).get("id")
    b_id = (pair.get("b") or {}).get("id")
    items = await list_items(db, user_id)
    by_id = {str(i.id): i for i in items}
    a_item = by_id.get(str(a_id)) if a_id else None
    b_item = by_id.get(str(b_id)) if b_id else None
    if a_item is not None and b_item is not None:
        merged = dict(a_item.details or {})
        for k, v in (b_item.details or {}).items():
            if v and not merged.get(k):
                merged[k] = v
        a_item.details = merged
        await db.commit()
        try:
            await delete_item(db, user_id, uuid.UUID(str(b_id)))
        except Exception:
            log.warning("onboarding_duplicate_merge_delete_failed", stage="merge")
        return f"Merged into one {category} entry — “{a_title}”."
    return f"Treated those as the same {category} entry."


def _next_question_after_dup(summary: list[dict]) -> str:
    q = ack_followup_question(summary)
    # Prefer a concrete What/How/Which follow-up.
    if q.startswith("What") or q.startswith("How") or q.startswith("Which"):
        return q
    return "Which project or skill should we explore next?"


async def chat(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    message: str,
    request_id: str | None = None,
    already_finished: bool = False,
    conversation_mode: str | None = None,
    message_id: str | None = None,
) -> dict:
    started = time.monotonic()
    uid = str(user.id)
    mid = (message_id or "").strip()[:80] or None
    settings = get_settings()

    if mid:
        cached = await conversation_store.get_idempotent_chat_reply(mongo_db, uid, mid)
        if cached:
            log.info(
                "onboarding_chat_timing",
                stage="idempotent_hit",
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            return cached

    from fastapi import HTTPException

    retry_in = await conversation_store.check_chat_rate_limit(
        mongo_db,
        uid,
        limit=settings.onboarding_chat_rpm,
        window_seconds=settings.onboarding_chat_rpm_window_seconds,
    )
    if retry_in is not None:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "You're sending messages a bit too quickly. Please wait a moment.",
                "cause": "rate_limited",
                "retry_after_seconds": int(retry_in) + 1,
            },
        )

    lock_key = mid or "anon"
    if not await conversation_store.try_acquire_chat_lock(mongo_db, uid, lock_key):
        raise HTTPException(
            status_code=429,
            detail={
                "message": "A reply is already in progress. Please wait a moment.",
                "cause": "rate_limited",
                "retry_after_seconds": 3,
            },
        )

    offer: dict | None = None
    try:
        if mid:
            cached = await conversation_store.get_idempotent_chat_reply(
                mongo_db, uid, mid
            )
            if cached:
                return cached

        t0 = time.monotonic()
        history = await conversation_store.get_messages(mongo_db, uid, limit=24)
        # Retries after a gateway failure must not duplicate the trailing user turn.
        last = history[-1] if history else None
        if not (
            last
            and last.get("role") == "user"
            and str(last.get("content") or "") == message
        ):
            await conversation_store.append_message(mongo_db, uid, "user", message)
            history = await conversation_store.get_messages(mongo_db, uid, limit=24)
        items = await list_items(db, user.id)
        summary = await vault_summary(db, user.id)
        coach_ctx = await conversation_store.get_coach_context(mongo_db, uid)
        log.info(
            "onboarding_chat_timing",
            stage="db_mongo_reads",
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )
        bg = infer_candidate_background(summary)
        if _message_signals_skip(message):
            coach_ctx = await conversation_store.merge_coach_context(
                mongo_db,
                uid,
                {
                    "proceed_to_goals": True,
                    "answers_received": (coach_ctx.get("answers_received") or [])
                    + [message.strip()[:180]],
                },
            )
        duplicates = find_near_duplicates(items)
        gaps = compute_profile_gaps(summary, coach_context=coach_ctx)
        prefs = await conversation_store.get_preparation_preferences(mongo_db, uid)
        mode = conversation_mode or await conversation_store.get_conversation_mode(
            mongo_db, uid
        )
        phase = derive_phase(
            vault_summary=summary,
            preferences=prefs,
            already_finished=already_finished,
            coach_context=coach_ctx,
        )

        turn: dict | None = None
        created: list = []
        updated: list = []
        path = "llm"
        offer_already = await conversation_store.get_start_offer_shown(mongo_db, uid)

        # 1) Deterministic pending-duplicate answers (no LLM).
        dup_decision = (
            classify_duplicate_answer(message)
            if recent_duplicate_prompt(history)
            else None
        )
        if dup_decision:
            path = "duplicate_resolve"
            if duplicates:
                confirm = await _apply_duplicate_decision(
                    db, user.id, dup_decision, duplicates[0]
                )
                summary = await vault_summary(db, user.id)
            elif dup_decision == "keep_both":
                confirm = "Kept both entries as you asked."
            else:
                confirm = "Treated those as the same entry."
            follow = _next_question_after_dup(summary)
            turn = OnboardingTurn(
                reply=ensure_nonempty_reply(
                    f"{confirm} {follow}",
                    vault_summary=summary,
                    duplicates_resolved=dup_decision,
                ),
                phase="goals" if vault_is_ready(summary, coach_ctx) else "profile",
                show_goal_menu=False,
            ).model_dump()
            log.info(
                "onboarding_chat_stage",
                stage="duplicate_resolve",
                cause=dup_decision,
            )

        # 2) Acknowledgement-only → one concrete next question (no LLM).
        elif is_ack_only(message):
            path = "ack_followup"
            turn = OnboardingTurn(
                reply=ack_followup_question(summary),
                phase=phase if phase in ("profile", "goals", "ready") else "profile",
                show_goal_menu=phase == "goals" and not prefs.get("interests"),
            ).model_dump()
            log.info("onboarding_chat_stage", stage="ack_followup", cause="ack_only")

        # 3) Practise / interview intent → no LLM; offer start popup.
        elif (practise := classify_practise_intent(message, summary)):
            path = "practise_intent"
            subject = practise["subject"]
            turn = OnboardingTurn(
                reply=practise_followup_reply(subject),
                phase=phase if phase in ("profile", "goals", "ready") else "profile",
                show_goal_menu=False,
            ).model_dump()
            if not offer_already:
                offer = {
                    "subject": subject,
                    "track_type": practise.get("track_type") or "topic",
                    "reason": "practise",
                }
            log.info(
                "onboarding_chat_stage",
                stage="practise_intent",
                cause="deterministic",
            )

        # 4) Normal LLM turn (single structured call).
        else:
            resume_options = build_resume_goal_options(summary)
            graph = build_onboarding_graph(turn_runner=run_onboarding_turn)
            t_llm = time.monotonic()
            try:
                result = await graph.ainvoke(
                    {
                        "message": message,
                        "history": history,
                        "vault_summary": summary,
                        "possible_duplicates": duplicates,
                        "profile_gaps": gaps,
                        "preparation_preferences": prefs,
                        "available_skills": resume_options.get("suggested_skills")
                        or _skill_titles(summary),
                        "available_projects": resume_options.get("suggested_projects")
                        or _project_titles(summary),
                        "resume_goal_options": resume_options,
                        "candidate_background": bg,
                        "coach_context": coach_ctx,
                        "conversation_mode": mode,
                        "already_finished": already_finished,
                        "phase": phase,
                        "meta": {"user_id": uid, "request_id": request_id},
                    }
                )
                turn = result["turn"]
            except LLMGatewayError as exc:
                log.warning(
                    "onboarding_chat_stage",
                    stage="llm",
                    cause=getattr(exc.cause, "value", "gateway_error"),
                    status_code=exc.status_code,
                    provider_code=exc.provider_code,
                    retry_after_seconds=exc.retry_after_seconds,
                    elapsed_ms=int((time.monotonic() - t_llm) * 1000),
                )
                raise
            except Exception as exc:
                log.warning(
                    "onboarding_chat_stage",
                    stage="llm_or_db",
                    cause=type(exc).__name__,
                    elapsed_ms=int((time.monotonic() - t_llm) * 1000),
                )
                raise
            log.info(
                "onboarding_chat_timing",
                stage="llm_total",
                elapsed_ms=int((time.monotonic() - t_llm) * 1000),
            )

            created, updated = await upsert_extracted_items(
                db,
                user.id,
                [ExtractedItem(**i) for i in (turn.get("extracted_items") or [])],
                "onboarding_chat",
            )

            prep_update = turn.get("preparation_update")
            if prep_update:
                prefs = merge_preferences(prefs, prep_update)
                prefs = await conversation_store.set_preparation_preferences(
                    mongo_db, uid, prefs
                )

        assert turn is not None
        turn["reply"] = ensure_nonempty_reply(
            turn.get("reply") or "",
            vault_summary=summary,
        )
        await conversation_store.append_message(
            mongo_db, uid, "assistant", turn["reply"]
        )

        asked = list(coach_ctx.get("asked_questions") or [])
        fp = turn.get("_question_fingerprint") or ""
        if not fp:
            from app.agents.onboarding import _question_fingerprint

            fp = _question_fingerprint(turn["reply"])
            turn["_question_fingerprint"] = fp
        if fp and fp not in asked:
            asked.append(fp)
        confirmed = list(coach_ctx.get("confirmed_facts") or [])
        for item in created + updated:
            title = f"{item.category}:{item.title}"
            if title not in confirmed:
                confirmed.append(title)
        answers = list(coach_ctx.get("answers_received") or [])
        if message.strip():
            answers.append(message.strip()[:180])
        await conversation_store.merge_coach_context(
            mongo_db,
            uid,
            {
                "background": bg,
                "asked_questions": asked[-40:],
                "confirmed_facts": confirmed[-40:],
                "answers_received": answers[-40:],
                "current_topic": turn.get("phase"),
                "proceed_to_goals": bool(coach_ctx.get("proceed_to_goals"))
                or turn.get("phase") in ("goals", "ready"),
            },
        )

        refreshed = await vault_summary(db, user.id)
        coach_ctx = await conversation_store.get_coach_context(mongo_db, uid)
        phase_out = turn.get("phase") or derive_phase(
            vault_summary=refreshed,
            preferences=prefs,
            already_finished=already_finished,
            coach_context=coach_ctx,
        )
        payload = {
            "reply": turn["reply"],
            "items_created": [
                {"id": str(i.id), "category": i.category, "title": i.title}
                for i in created
            ],
            "items_updated": [
                {"id": str(i.id), "category": i.category, "title": i.title}
                for i in updated
            ],
            "onboarding_complete": preferences_ready(prefs) or already_finished,
            "phase": phase_out,
            "show_goal_menu": bool(turn.get("show_goal_menu"))
            or (phase_out == "goals" and not prefs.get("interests")),
            "preparation_preferences": prefs,
            "conversation_mode": mode,
            "show_starters": _should_show_starters(history, phase_out, already_finished),
            "candidate_background": bg,
            "coach_context": coach_ctx,
            "offer_start_interview": offer,
        }
        if mid:
            await conversation_store.save_idempotent_chat_reply(
                mongo_db, uid, mid, payload
            )
        if offer:
            await conversation_store.mark_start_offer_shown(mongo_db, uid)
        log.info(
            "onboarding_chat_timing",
            stage="total",
            path=path,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
        return payload
    finally:
        await conversation_store.release_chat_lock(mongo_db, uid, lock_key)


async def start_conversation_starter(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    starter_id: str,
    *,
    already_finished: bool = False,
    request_id: str | None = None,
) -> dict:
    starter = CONVERSATION_STARTERS.get(starter_id)
    if starter is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"Unknown starter: {starter_id}")
    await conversation_store.set_conversation_mode(mongo_db, str(user.id), starter_id)
    return await chat(
        db,
        mongo_db,
        user,
        starter["message"],
        request_id=request_id,
        already_finished=already_finished,
        conversation_mode=starter_id,
    )


def _should_show_starters(
    history: list[dict], phase: str, already_finished: bool
) -> bool:
    if already_finished or phase == "ready":
        return False
    # Show after an automatic welcome (or any short history) while exploring.
    if not history:
        return False
    assistant_msgs = [m for m in history if m.get("role") == "assistant"]
    user_msgs = [m for m in history if m.get("role") == "user"]
    if not assistant_msgs:
        return False
    # Hide once the user is deep in conversation.
    return len(user_msgs) < 3


async def save_goals(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    update: dict,
    *,
    already_finished: bool = False,
    request_id: str | None = None,
) -> dict:
    """Persist goal chip selections, then ask one coach follow-up."""
    summary = await vault_summary(db, user.id)
    coach_ctx = await conversation_store.get_coach_context(mongo_db, str(user.id))
    if not vault_is_ready(summary, coach_ctx) and not already_finished:
        # Choosing goals is always allowed — mark proceed so empty/optional vaults unlock.
        coach_ctx = await conversation_store.merge_coach_context(
            mongo_db, str(user.id), {"proceed_to_goals": True}
        )

    current = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    # Chip posts should not auto-confirm unless caller sets confirmed.
    merged = merge_preferences(current, update)
    if update.get("confirmed") is not True:
        merged["confirmed"] = False
    prefs = await conversation_store.set_preparation_preferences(
        mongo_db, str(user.id), merged
    )

    labels = [
        next((label for iid, label in GOAL_INTERESTS if iid == i), i)
        for i in prefs["interests"]
    ]
    user_line = (
        "I want to focus on: " + ", ".join(labels)
        if labels
        else "I'd like to choose my interview preparation focus."
    )
    # Prefer the coach LLM; if the gateway is rate-limited/down, keep goals saved.
    try:
        return await chat(
            db,
            mongo_db,
            user,
            user_line,
            request_id=request_id,
            already_finished=already_finished,
        )
    except Exception as exc:
        if not isinstance(exc, LLMGatewayError):
            log.error(
                "save_goals_coach_failed",
                request_id=request_id,
                user_id=str(user.id),
                error=str(exc)[:200],
                exc_info=True,
            )
        history = await conversation_store.get_messages(mongo_db, str(user.id), limit=4)
        last = history[-1] if history else None
        if not (
            last
            and last.get("role") == "user"
            and last.get("content") == user_line
        ):
            await conversation_store.append_message(
                mongo_db, str(user.id), "user", user_line
            )
        summary = await vault_summary(db, user.id)
        reply = goals_followup_reply(prefs, summary)
        await conversation_store.append_message(
            mongo_db, str(user.id), "assistant", reply
        )
        phase = derive_phase(
            vault_summary=summary,
            preferences=prefs,
            already_finished=already_finished,
        )
        mode = await conversation_store.get_conversation_mode(mongo_db, str(user.id))
        return {
            "reply": reply,
            "items_created": [],
            "items_updated": [],
            "onboarding_complete": preferences_ready(prefs) or already_finished,
            "phase": phase,
            "show_goal_menu": phase == "goals" and not prefs.get("interests"),
            "preparation_preferences": prefs,
            "conversation_mode": mode,
            "show_starters": False,
        }


async def confirm_goals(
    mongo_db: AsyncIOMotorDatabase,
    user: User,
) -> dict:
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    if not prefs.get("interests"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409,
            detail="Select at least one preparation interest first.",
        )
    prefs = merge_preferences(prefs, {"confirmed": True})
    prefs = await conversation_store.set_preparation_preferences(
        mongo_db, str(user.id), prefs
    )
    summary = summarize_preferences(prefs)
    await conversation_store.append_message(
        mongo_db,
        str(user.id),
        "assistant",
        f"Great — here's your preparation plan:\n{summary}\n\n"
        "When you're ready, tap Start Preparing to open your Tracks dashboard.",
    )
    return prefs


async def ensure_review_opener(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
) -> bool:
    """If the vault has data but chat has no welcome yet, seed one (idempotent)."""
    messages = await conversation_store.get_messages(mongo_db, str(user.id), limit=40)
    if any(message_looks_like_resume_welcome(m.get("content") or "") for m in messages):
        return False
    if messages:
        # Conversation already started manually — don't inject a late welcome.
        return False
    items = await list_items(db, user.id)
    if not items:
        return False
    await conversation_store.append_message(
        mongo_db, str(user.id), "assistant", build_profile_review_message(items)
    )
    return True


async def seed_resume_welcome(
    mongo_db: AsyncIOMotorDatabase,
    user_id: str,
    items: list,
) -> bool:
    """After successful resume extraction — one personalized welcome, never duplicated."""
    if not items:
        return False
    messages = await conversation_store.get_messages(mongo_db, user_id, limit=40)
    if any(message_looks_like_resume_welcome(m.get("content") or "") for m in messages):
        return False
    await conversation_store.append_message(
        mongo_db, user_id, "assistant", build_profile_review_message(items)
    )
    summary = [
        {
            "category": getattr(i, "category", ""),
            "title": getattr(i, "title", ""),
            "details": getattr(i, "details", None) or {},
        }
        for i in items
    ]
    await conversation_store.merge_coach_context(
        mongo_db,
        user_id,
        {
            "background": infer_candidate_background(summary),
            "proceed_to_goals": True,
        },
    )
    return True


async def ensure_goals_intro(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
) -> bool:
    """When vault is ready and goals are unset, seed the goals transition once."""
    summary = await vault_summary(db, user.id)
    coach_ctx = await conversation_store.get_coach_context(mongo_db, str(user.id))
    if not vault_is_ready(summary, coach_ctx):
        return False
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    if prefs.get("interests") or prefs.get("confirmed"):
        return False
    messages = await conversation_store.get_messages(mongo_db, str(user.id), limit=30)
    if any(GOALS_INTRO_MARKER in (m.get("content") or "") for m in messages):
        return False
    intro = goals_intro_message(summary)
    await conversation_store.append_message(mongo_db, str(user.id), "assistant", intro)
    return True


async def _assessed_subjects(db: AsyncSession, user_id) -> set[str]:
    """Subjects from completed interview reports — used only as evidence, not scores."""
    from sqlalchemy import select

    from app.models.feedback import FeedbackReport
    from app.models.track import Track

    rows = (
        await db.execute(
            select(Track.subject)
            .join(FeedbackReport, FeedbackReport.track_id == Track.id)
            .where(FeedbackReport.user_id == user_id)
        )
    ).all()
    return {str(r[0]).lower() for r in rows if r and r[0]}


async def _improvement_topics(db: AsyncSession, user_id) -> list[str]:
    """Topics from persisted interview feedback only — no invented proficiency."""
    from collections import Counter

    from sqlalchemy import select

    from app.models.feedback import FeedbackReport
    from app.models.track import Track

    rows = (
        await db.execute(
            select(FeedbackReport.content, Track.archived_at).join(
                Track, FeedbackReport.track_id == Track.id
            ).where(FeedbackReport.user_id == user_id)
        )
    ).all()
    counter: Counter[str] = Counter()
    for content, archived_at in rows:
        if archived_at is not None:
            continue
        payload = content if isinstance(content, dict) else {}
        for area in payload.get("improvement_areas") or []:
            text = str(area).strip()
            if text:
                counter[text] += 1
        for comp in payload.get("competency_assessments") or []:
            if not isinstance(comp, dict):
                continue
            name = str(comp.get("competency_name") or "").strip()
            level = str(comp.get("level") or "").lower()
            if name and level in ("weak", "developing"):
                counter[name] += 2
    return [name for name, _ in counter.most_common(5)]


async def _existing_tracks(db: AsyncSession, user_id) -> list[dict]:
    from sqlalchemy import select

    from app.models.track import Track

    rows = (
        await db.execute(
            select(Track.id, Track.subject).where(
                Track.user_id == user_id, Track.archived_at.is_(None)
            )
        )
    ).all()
    return [
        {"id": str(r[0]), "subject": str(r[1])}
        for r in rows
        if r and r[0] and r[1]
    ]


async def _existing_track_subjects(db: AsyncSession, user_id) -> set[str]:
    return {t["subject"] for t in await _existing_tracks(db, user_id)}


async def ensure_profile_review(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    *,
    force: bool = False,
) -> dict:
    """Build or refresh the post-onboarding review; persist without clobbering edits."""
    from app.services import interview_service

    items = await list_items(db, user.id)
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    previous = await conversation_store.get_profile_review(mongo_db, str(user.id)) or {}
    tracks = await _existing_tracks(db, user.id)
    open_sessions = await interview_service.list_open_sessions_for_user(db, user, limit=5)
    review = build_review(
        items,
        prefs,
        previous=previous,
        assessed_subjects=await _assessed_subjects(db, user.id),
        existing_tracks=tracks,
        existing_track_subjects={t["subject"] for t in tracks},
        open_sessions=open_sessions,
        improvement_topics=await _improvement_topics(db, user.id),
        force_summary=force,
    )
    # Refuse to persist an empty wipe over a previously useful review.
    if (
        previous.get("summary")
        and not (review.get("summary") or "").strip()
        and previous.get("roadmap")
        and not (review.get("roadmap") or [])
    ):
        return previous
    return await conversation_store.set_profile_review(mongo_db, str(user.id), review)


async def get_profile_review_payload(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    *,
    ensure: bool = True,
) -> dict:
    existing = await conversation_store.get_profile_review(mongo_db, str(user.id))
    if ensure and (
        user.onboarding_completed_at is not None
        or (existing and existing.get("summary"))
    ):
        return await ensure_profile_review(db, mongo_db, user)
    return existing or empty_review()


async def patch_profile_review(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    patch: dict,
) -> dict:
    current = await get_profile_review_payload(db, mongo_db, user, ensure=True)
    merged = merge_review_patch(current, patch)
    return await conversation_store.set_profile_review(mongo_db, str(user.id), merged)


async def start_recommended_track(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    *,
    request_id: str | None = None,
    subject: str | None = None,
    track_type: str | None = None,
) -> dict:
    """Create (or reuse) the recommended track and remember the selection."""
    from sqlalchemy import select

    from app.models.track import Track
    from app.services import track_service

    review = await ensure_profile_review(db, mongo_db, user)
    action = review.get("next_action") or {}
    use_subject = (subject or action.get("subject") or "").strip()
    use_type = (track_type or action.get("track_type") or "topic").strip()
    if not use_subject:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="No recommended track is available yet.")

    existing = (
        await db.execute(
            select(Track).where(
                Track.user_id == user.id,
                Track.archived_at.is_(None),
                Track.subject == use_subject,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        review["selected_next_track_id"] = str(existing.id)
        await conversation_store.set_profile_review(mongo_db, str(user.id), review)
        return {"track": track_service._track_dict(existing), "created": False, "review": review}

    created = await track_service.create_track_with_brief(
        db,
        user,
        track_type=use_type if use_type in ("topic", "role", "company_jd") else "topic",
        subject=use_subject,
        request_id=request_id,
    )
    track = created["track"]
    review["selected_next_track_id"] = track["id"]
    await conversation_store.set_profile_review(mongo_db, str(user.id), review)
    return {"track": track, "created": True, "review": review}


async def state_extras(db: AsyncSession, mongo_db: AsyncIOMotorDatabase, user: User) -> dict:
    summary = await vault_summary(db, user.id)
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    coach_ctx = await conversation_store.get_coach_context(mongo_db, str(user.id))
    finished = user.onboarding_completed_at is not None
    phase = derive_phase(
        vault_summary=summary,
        preferences=prefs,
        already_finished=finished,
        coach_context=coach_ctx,
    )
    history = await conversation_store.get_messages(mongo_db, str(user.id), limit=40)
    mode = await conversation_store.get_conversation_mode(mongo_db, str(user.id))
    review = None
    if finished:
        review = await get_profile_review_payload(db, mongo_db, user, ensure=True)
    resume_options = build_resume_goal_options(summary)
    gaps = compute_profile_gaps(summary, coach_context=coach_ctx)
    return {
        "phase": phase,
        "show_goal_menu": phase == "goals" and not prefs.get("interests"),
        "preparation_preferences": prefs,
        **resume_options,
        "next_goal_followup": next_goal_followup(prefs),
        "followups_complete": followups_complete(prefs),
        "recommended_tracks": recommend_track_seeds(prefs),
        "preparation_summary": summarize_preferences(prefs),
        "goals_ready": preferences_ready(prefs) or finished,
        "conversation_mode": mode,
        "coach_context": coach_ctx,
        "profile_gaps": gaps,
        "optional_categories": True,
        "show_starters": _should_show_starters(history, phase, finished),
        "conversation_starters": [
            {"id": sid, "label": meta["label"], "description": meta["description"]}
            for sid, meta in CONVERSATION_STARTERS.items()
        ],
        "has_resume_welcome": any(
            message_looks_like_resume_welcome(m.get("content") or "") for m in history
        ),
        "profile_review": review,
    }
