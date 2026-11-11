from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import (
    ExtractedItem,
    build_onboarding_graph,
    compute_profile_gaps,
    derive_phase,
    vault_is_ready,
)
from app.models.user import User
from app.services import conversation_store
from app.gateway.llm import LLMGatewayError
from app.services.preparation_goals import (
    GOALS_INTRO,
    GOAL_INTERESTS,
    goals_followup_reply,
    merge_preferences,
    preferences_ready,
    recommend_track_seeds,
    summarize_preferences,
)
from app.services.preparation_review import (
    build_review,
    empty_review,
    merge_review_patch,
)
from app.services.vault_service import (
    build_profile_review_message,
    find_near_duplicates,
    list_items,
    message_looks_like_resume_welcome,
    upsert_extracted_items,
    vault_summary,
)

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
    return [i["title"] for i in summary if i.get("category") == "skill"]


def _project_titles(summary: list[dict]) -> list[str]:
    return [i["title"] for i in summary if i.get("category") == "project"]


async def chat(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    message: str,
    request_id: str | None = None,
    already_finished: bool = False,
    conversation_mode: str | None = None,
) -> dict:
    await conversation_store.append_message(mongo_db, str(user.id), "user", message)
    history = await conversation_store.get_messages(mongo_db, str(user.id), limit=24)
    items = await list_items(db, user.id)
    summary = await vault_summary(db, user.id)
    duplicates = find_near_duplicates(items)
    gaps = compute_profile_gaps(summary)
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    mode = conversation_mode or await conversation_store.get_conversation_mode(
        mongo_db, str(user.id)
    )
    phase = derive_phase(
        vault_summary=summary, preferences=prefs, already_finished=already_finished
    )

    graph = build_onboarding_graph(turn_runner=run_onboarding_turn)
    result = await graph.ainvoke(
        {
            "message": message,
            "history": history,
            "vault_summary": summary,
            "possible_duplicates": duplicates,
            "profile_gaps": gaps,
            "preparation_preferences": prefs,
            "available_skills": _skill_titles(summary),
            "available_projects": _project_titles(summary),
            "conversation_mode": mode,
            "already_finished": already_finished,
            "phase": phase,
            "meta": {"user_id": str(user.id), "request_id": request_id},
        }
    )
    turn = result["turn"]

    created, updated = await upsert_extracted_items(
        db,
        user.id,
        [ExtractedItem(**i) for i in turn["extracted_items"]],
        "onboarding_chat",
    )

    prep_update = turn.get("preparation_update")
    if prep_update:
        prefs = merge_preferences(prefs, prep_update)
        prefs = await conversation_store.set_preparation_preferences(
            mongo_db, str(user.id), prefs
        )

    await conversation_store.append_message(mongo_db, str(user.id), "assistant", turn["reply"])

    refreshed = await vault_summary(db, user.id)
    phase_out = turn.get("phase") or derive_phase(
        vault_summary=refreshed, preferences=prefs, already_finished=already_finished
    )
    # Seed goals intro once when entering goals with empty interests.
    if (
        phase_out == "goals"
        and not prefs.get("interests")
        and GOALS_INTRO not in turn["reply"]
    ):
        # UI also shows the menu; keep agent reply as-is.
        pass

    return {
        "reply": turn["reply"],
        "items_created": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in created
        ],
        "items_updated": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in updated
        ],
        "onboarding_complete": preferences_ready(prefs) or already_finished,
        "phase": phase_out,
        "show_goal_menu": bool(turn.get("show_goal_menu"))
        or (phase_out == "goals" and not prefs.get("interests")),
        "preparation_preferences": prefs,
        "conversation_mode": mode,
        "show_starters": _should_show_starters(history, phase_out, already_finished),
    }


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
    if not vault_is_ready(summary) and not already_finished:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409,
            detail="Finish your profile vault before choosing preparation goals.",
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
    except LLMGatewayError:
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
        reply = goals_followup_reply(prefs)
        await conversation_store.append_message(
            mongo_db, str(user.id), "assistant", reply
        )
        summary = await vault_summary(db, user.id)
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
    return True


async def ensure_goals_intro(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
) -> bool:
    """When vault is ready and goals are unset, seed the goals transition once."""
    summary = await vault_summary(db, user.id)
    if not vault_is_ready(summary):
        return False
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    if prefs.get("interests") or prefs.get("confirmed"):
        return False
    messages = await conversation_store.get_messages(mongo_db, str(user.id), limit=30)
    if any(GOALS_INTRO in (m.get("content") or "") for m in messages):
        return False
    await conversation_store.append_message(mongo_db, str(user.id), "assistant", GOALS_INTRO)
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
    finished = user.onboarding_completed_at is not None
    phase = derive_phase(
        vault_summary=summary, preferences=prefs, already_finished=finished
    )
    history = await conversation_store.get_messages(mongo_db, str(user.id), limit=40)
    mode = await conversation_store.get_conversation_mode(mongo_db, str(user.id))
    review = None
    if finished:
        review = await get_profile_review_payload(db, mongo_db, user, ensure=True)
    return {
        "phase": phase,
        "show_goal_menu": phase == "goals" and not prefs.get("interests"),
        "preparation_preferences": prefs,
        "goal_interest_options": [
            {"id": i, "label": label} for i, label in GOAL_INTERESTS
        ],
        "suggested_skills": _skill_titles(summary),
        "suggested_projects": _project_titles(summary),
        "recommended_tracks": recommend_track_seeds(prefs),
        "preparation_summary": summarize_preferences(prefs),
        "goals_ready": preferences_ready(prefs) or finished,
        "conversation_mode": mode,
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
