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
    classify_topic_focus,
    compute_profile_gaps,
    continue_topic_reply,
    derive_phase,
    ensure_nonempty_reply,
    extract_pending_topic,
    infer_question_intent,
    _last_ask_awaits_selection,
    coach_action_requires_deterministic_reply,
    decide_conversational_action,
    extract_focus_shift_from_reply,
    is_ack_only,
    is_negative_or_skip,
    practise_followup_reply,
    recent_duplicate_prompt,
    render_coach_action_reply,
    resolve_topic_confirmation,
    suggested_next_topics,
    topic_focus_reply,
    vault_is_ready,
    wants_topic_switch,
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


def _message_signals_skip(message: str, coach_context: dict | None = None) -> bool:
    """True only when context says the candidate is leaving the topic (not bare IDK)."""
    action = decide_conversational_action(
        message, coach_context=coach_context or {}, mode="guided"
    )["action"]
    return action in {"change_topic", "pause"}


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
        if _message_signals_skip(message, coach_ctx):
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
        focus_patch: dict = {}
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
                    coach_context=coach_ctx,
                ),
                phase="goals" if vault_is_ready(summary, coach_ctx) else "profile",
                show_goal_menu=False,
            ).model_dump()
            log.info(
                "onboarding_chat_stage",
                stage="duplicate_resolve",
                cause=dup_decision,
            )

        # 2) Confirm a previously offered topic ("yes" after "Would you like…").
        elif (confirmed := resolve_topic_confirmation(
            message, summary, coach_ctx, history
        )):
            path = "topic_confirm"
            title = confirmed["title"]
            turn = OnboardingTurn(
                reply=topic_focus_reply(confirmed, coach_context=coach_ctx),
                phase=phase if phase in ("profile", "goals", "ready") else "profile",
                show_goal_menu=False,
            ).model_dump()
            turn["_focus_topic"] = title
            turn["_focus_kind"] = confirmed.get("kind") or confirmed.get("category")
            turn["_focus_locked"] = True
            focus_patch = {"pending_followup": ""}
            log.info(
                "onboarding_chat_stage",
                stage="topic_confirm",
                cause="affirmative",
                topic=title[:80],
            )

        # 3) Explicit topic selection / switch (any vault category) — no LLM.
        elif (focused := classify_topic_focus(
            message, summary, coach_context=coach_ctx
        )) and (
            wants_topic_switch(message)
            or not coach_ctx.get("focus_locked")
            or (focused.get("title") or "").lower()
            != (coach_ctx.get("current_topic") or "").lower()
        ):
            path = "topic_focus"
            title = focused["title"]
            turn = OnboardingTurn(
                reply=topic_focus_reply(focused, coach_context=coach_ctx),
                phase=phase if phase in ("profile", "goals", "ready") else "profile",
                show_goal_menu=False,
            ).model_dump()
            turn["_focus_topic"] = title
            turn["_focus_kind"] = focused.get("kind") or focused.get("category")
            turn["_focus_locked"] = True
            focus_patch = {"pending_followup": ""}
            log.info(
                "onboarding_chat_stage",
                stage="topic_focus",
                cause="deterministic",
                topic=title[:80],
                kind=turn.get("_focus_kind"),
            )

        # 4) Contextual turn decision for uncertainty / move-on / pause / hints.
        #    Bare "I don't know" simplifies on the same topic; explicit move-on changes it.
        #    advance / rich follow_up fall through to the LLM stages below.
        elif coach_action_requires_deterministic_reply(
            (
                _coach_decision := decide_conversational_action(
                    message, coach_context=coach_ctx, mode="guided"
                )
            )["action"]
        ):
            prev = str(coach_ctx.get("current_topic") or "")
            action = _coach_decision["action"]
            path = f"coach_{action}"
            soft_reply = render_coach_action_reply(
                action,
                coach_context=coach_ctx,
                vault_summary=summary,
                mode="guided",
            )
            turn = OnboardingTurn(
                reply=soft_reply,
                phase=phase if phase in ("profile", "goals", "ready") else "profile",
                show_goal_menu=False,
            ).model_dump()
            try:
                streak = int(coach_ctx.get("uncertainty_streak") or 0)
            except (TypeError, ValueError):
                streak = 0
            if action == "pause":
                turn["_clear_focus"] = True
                focus_patch = {"pending_followup": "", "uncertainty_streak": 0}
            elif action == "change_topic":
                turn["_clear_focus"] = True
                skipped_cats = list(coach_ctx.get("skipped_categories") or [])
                if prev:
                    marker = f"topic:{prev}"[:120]
                    if marker not in skipped_cats:
                        skipped_cats.append(marker)
                focus_patch = {
                    "pending_followup": "",
                    "skipped_categories": skipped_cats[-20:],
                    "uncertainty_streak": 0,
                }
                skipped_titles = [
                    str(x).split(":", 1)[-1]
                    for x in skipped_cats
                    if isinstance(x, str) and x.startswith("topic:")
                ]
                opts = suggested_next_topics(
                    summary, prev, exclude_titles=skipped_titles, limit=1
                )
                if opts:
                    nxt = opts[0]
                    turn["_focus_topic"] = nxt["title"]
                    turn["_focus_kind"] = nxt["kind"]
                    turn["_focus_locked"] = True
                    turn["_clear_focus"] = False
            else:
                # simplify / guide / clarify — stay on topic; never skill-menu.
                bump = 1 if action in ("simplify", "guide") else 0
                try:
                    clarify_n = int(coach_ctx.get("clarify_count") or 0)
                except (TypeError, ValueError):
                    clarify_n = 0
                focus_patch = {
                    "pending_followup": "",
                    "uncertainty_streak": streak + bump,
                }
                if action == "clarify":
                    focus_patch["clarify_count"] = clarify_n + 1
                if prev:
                    turn["_focus_topic"] = prev
                    turn["_focus_kind"] = coach_ctx.get("focus_kind") or "subject"
                    turn["_focus_locked"] = True
            log.info(
                "onboarding_chat_stage",
                stage=path,
                cause=_coach_decision.get("reason"),
                action=action,
                topic=prev[:80] if prev else None,
            )

        # 5) Acknowledgement-only → continue current topic (never random vault[0]
        #    and never re-ask the same confirmation).
        elif is_ack_only(message):
            path = "ack_followup"
            reply = (
                continue_topic_reply(coach_ctx, summary)
                or ack_followup_question(summary, coach_ctx)
            )
            turn = OnboardingTurn(
                reply=reply,
                phase=phase if phase in ("profile", "goals", "ready") else "profile",
                show_goal_menu=phase == "goals" and not prefs.get("interests"),
            ).model_dump()
            # Affirmative after a topic offer: lock the pending topic if not yet locked.
            pending = (coach_ctx.get("pending_followup") or "").strip()
            if (
                (coach_ctx.get("last_question_intent") or "") == "confirm_topic"
                and pending
                and not coach_ctx.get("focus_locked")
            ):
                turn["_focus_topic"] = pending
                turn["_focus_kind"] = "subject"
                turn["_focus_locked"] = True
                focus_patch = {"pending_followup": ""}
            log.info(
                "onboarding_chat_stage",
                stage="ack_followup",
                cause="ack_only",
                topic=(coach_ctx.get("current_topic") or pending or "")[:80] or None,
            )

        # 6) Practise / interview intent → no LLM; offer start popup.
        elif (practise := classify_practise_intent(message, summary)):
            path = "practise_intent"
            subject = practise["subject"]
            turn = OnboardingTurn(
                reply=practise_followup_reply(subject),
                phase=phase if phase in ("profile", "goals", "ready") else "profile",
                show_goal_menu=False,
            ).model_dump()
            turn["_focus_topic"] = subject
            turn["_focus_kind"] = "subject"
            turn["_focus_locked"] = True
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

        # 7) Normal LLM turn (single structured call).
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
            coach_context=coach_ctx,
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

        clear_focus = bool(turn.pop("_clear_focus", False))
        new_focus = turn.pop("_focus_topic", None)
        new_kind = turn.pop("_focus_kind", None)
        locked_flag = turn.pop("_focus_locked", None)
        if clear_focus:
            topic_out: str | None = None
            kind_out: str | None = None
            locked_out = False
        elif new_focus:
            topic_out = str(new_focus).strip()[:120]
            kind_out = (new_kind or coach_ctx.get("focus_kind") or "subject")
            locked_out = True if locked_flag is None else bool(locked_flag)
        elif coach_ctx.get("focus_locked") and coach_ctx.get("current_topic"):
            # Preserve explicit selection across turns (including LLM path).
            topic_out = coach_ctx.get("current_topic")
            kind_out = coach_ctx.get("focus_kind")
            locked_out = True
        else:
            topic_out = coach_ctx.get("current_topic")
            kind_out = coach_ctx.get("focus_kind")
            locked_out = bool(coach_ctx.get("focus_locked"))

        reply_text = turn["reply"]
        # If the assistant pivoted to a new subject while state still held the old
        # lock, adopt the new focus so the next short answer cannot revive the old topic.
        if locked_out and topic_out and reply_text:
            prior_topic = str(coach_ctx.get("current_topic") or topic_out).strip()
            shifted = extract_focus_shift_from_reply(reply_text, prior_topic)
            reply_low = reply_text.lower()
            prior_low = prior_topic.lower()
            left_prior = bool(prior_low) and prior_low not in reply_low
            pivot_language = any(
                p in reply_low
                for p in (
                    "move the focus",
                    "would you prefer",
                    "switch",
                    "another area",
                    "different topic",
                    "instead",
                )
            ) or _last_ask_awaits_selection(reply_text)

            def _mark_prior_skipped() -> None:
                skipped_cats = list(
                    focus_patch.get("skipped_categories")
                    or coach_ctx.get("skipped_categories")
                    or []
                )
                prev_marker = f"topic:{prior_topic}"[:120]
                if prev_marker not in skipped_cats and prior_topic:
                    skipped_cats.append(prev_marker)
                    focus_patch["skipped_categories"] = skipped_cats[-20:]
                    focus_patch["uncertainty_streak"] = 0
                    focus_patch["clarify_count"] = 0

            if shifted and shifted.lower() != prior_low:
                topic_out = shifted
                kind_out = kind_out or coach_ctx.get("focus_kind") or "subject"
                locked_out = True
                _mark_prior_skipped()
            elif left_prior and pivot_language:
                # Pivot detected but label extraction failed — unlock so stale
                # clarify cannot revive the abandoned topic on the next turn.
                locked_out = False
                _mark_prior_skipped()
        intent = infer_question_intent(reply_text)
        pending = extract_pending_topic(reply_text) if intent == "confirm_topic" else None
        ctx_update = {
            "background": bg,
            "asked_questions": asked[-40:],
            "confirmed_facts": confirmed[-40:],
            "answers_received": answers[-40:],
            "current_topic": topic_out if topic_out is not None else "",
            "focus_kind": kind_out if kind_out is not None else "",
            "focus_locked": locked_out,
            "last_assistant_question": reply_text[:320],
            "last_question_intent": intent,
            "pending_followup": pending or focus_patch.get("pending_followup") or "",
            "proceed_to_goals": bool(coach_ctx.get("proceed_to_goals"))
            or turn.get("phase") in ("goals", "ready"),
        }
        if focus_patch:
            ctx_update.update(focus_patch)
        elif len(message.strip()) > 40:
            # Substantive turns clear uncertainty streak unless stage-4 already set it.
            ctx_update["uncertainty_streak"] = 0
        await conversation_store.merge_coach_context(mongo_db, uid, ctx_update)

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
    sync_result: dict | None = None,
) -> dict:
    """After successful resume processing — start a fresh conversation with a sync-aware welcome.

    Archives the prior active thread (never deletes). Skips only when the active thread is
    already a fresh resume-upload welcome with no user turns (idempotent double-call guard).
    """
    from app.services.vault_service import build_resume_sync_welcome

    meta = await conversation_store.get_active_conversation_meta(mongo_db, user_id)
    messages = await conversation_store.get_messages(mongo_db, user_id, limit=40)
    if (
        meta.get("reason") == "resume_upload"
        and len(messages) == 1
        and (messages[0] or {}).get("role") == "assistant"
        and message_looks_like_resume_welcome((messages[0] or {}).get("content") or "")
    ):
        return {
            "seeded": False,
            "conversation_id": meta.get("conversation_id"),
            "reason": "already_fresh_resume_conversation",
        }

    summary = [
        {
            "category": getattr(i, "category", ""),
            "title": getattr(i, "title", ""),
            "details": getattr(i, "details", None) or {},
        }
        for i in items
    ]
    welcome = build_resume_sync_welcome(sync_result, items)
    started = await conversation_store.start_new_conversation(
        mongo_db,
        user_id,
        title="Resume upload",
        reason="resume_upload",
        welcome=welcome,
        reset_coach=True,
        coach_patch={
            "background": infer_candidate_background(summary) if summary else {},
            # Verify-first: do not jump to goals/personalization yet.
            "proceed_to_goals": False,
            "profile_verified": False,
        },
    )
    return {"seeded": True, **started}


async def ensure_goals_intro(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
) -> bool:
    """When vault is ready and goals are unset, seed the goals transition once.

    Gated on profile_verified so New Chat / resume upload cannot auto-personalize
    before the candidate confirms extraction.
    """
    uid = str(user.id)
    summary = await vault_summary(db, user.id)
    coach_ctx = await conversation_store.get_coach_context(mongo_db, uid)
    if not coach_ctx.get("profile_verified"):
        return False
    if not vault_is_ready(summary, coach_ctx):
        return False
    prefs = await conversation_store.get_preparation_preferences(mongo_db, uid)
    if prefs.get("interests") or prefs.get("confirmed"):
        return False
    messages = await conversation_store.get_messages(mongo_db, uid, limit=30)
    if any(GOALS_INTRO_MARKER in (m.get("content") or "") for m in messages):
        return False
    intro = goals_intro_message(summary)
    await conversation_store.append_message(mongo_db, uid, "assistant", intro)
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
    """Build or refresh the post-onboarding review; persist without clobbering edits.

    Uses the Shared Candidate Intelligence Snapshot when available so vault claims,
    goals, and interview-demonstrated evidence stay separated in the review.
    Falls back to legacy assessed/improvement helpers if the snapshot load fails.
    """
    from app.services import interview_service

    items = await list_items(db, user.id)
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    previous = await conversation_store.get_profile_review(mongo_db, str(user.id)) or {}
    tracks = await _existing_tracks(db, user.id)
    open_sessions = await interview_service.list_open_sessions_for_user(db, user, limit=5)

    snapshot = None
    try:
        from app.services.candidate_intelligence import get_candidate_intelligence_for_user

        snapshot = await get_candidate_intelligence_for_user(
            db, user.id, mongo_db=mongo_db, user=user
        )
    except Exception:  # noqa: BLE001 — review must still work without intelligence
        snapshot = None

    assessed = await _assessed_subjects(db, user.id)
    improvements = await _improvement_topics(db, user.id)
    if snapshot is not None:
        from app.services.preparation_review import (
            assessed_concepts_from_snapshot,
            improvement_topics_from_snapshot,
        )

        assessed = assessed | assessed_concepts_from_snapshot(snapshot)
        snap_improvements = improvement_topics_from_snapshot(snapshot)
        if snap_improvements:
            # Prefer snapshot list (already deduped); keep legacy only as filler.
            merged: list[str] = []
            seen: set[str] = set()
            for topic in [*snap_improvements, *improvements]:
                key = str(topic).strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append(str(topic).strip())
                if len(merged) >= 5:
                    break
            improvements = merged

    review = build_review(
        items,
        prefs,
        previous=previous,
        assessed_subjects=assessed,
        existing_tracks=tracks,
        existing_track_subjects={t["subject"] for t in tracks},
        open_sessions=open_sessions,
        improvement_topics=improvements,
        candidate_intelligence=snapshot,
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
        "profile_verified": bool(coach_ctx.get("profile_verified")),
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
