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
from app.services.preparation_goals import (
    GOALS_INTRO,
    GOAL_INTERESTS,
    merge_preferences,
    preferences_ready,
    recommend_track_seeds,
    summarize_preferences,
)
from app.services.vault_service import (
    find_near_duplicates,
    list_items,
    upsert_extracted_items,
    vault_summary,
)


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
) -> dict:
    await conversation_store.append_message(mongo_db, str(user.id), "user", message)
    history = await conversation_store.get_messages(mongo_db, str(user.id), limit=24)
    items = await list_items(db, user.id)
    summary = await vault_summary(db, user.id)
    duplicates = find_near_duplicates(items)
    gaps = compute_profile_gaps(summary)
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
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
    }


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
    # Run through chat so history + follow-up stay consistent.
    return await chat(
        db,
        mongo_db,
        user,
        user_line,
        request_id=request_id,
        already_finished=already_finished,
    )


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
    """If the vault has data but chat is empty, seed a review welcome message."""
    from app.services.vault_service import build_profile_review_message

    messages = await conversation_store.get_messages(mongo_db, str(user.id), limit=5)
    if messages:
        return False
    items = await list_items(db, user.id)
    if not items:
        return False
    await conversation_store.append_message(
        mongo_db, str(user.id), "assistant", build_profile_review_message(items)
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


async def state_extras(db: AsyncSession, mongo_db: AsyncIOMotorDatabase, user: User) -> dict:
    summary = await vault_summary(db, user.id)
    prefs = await conversation_store.get_preparation_preferences(mongo_db, str(user.id))
    finished = user.onboarding_completed_at is not None
    phase = derive_phase(
        vault_summary=summary, preferences=prefs, already_finished=finished
    )
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
    }
