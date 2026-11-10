from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import (
    ExtractedItem,
    build_onboarding_graph,
    compute_profile_gaps,
)
from app.models.user import User
from app.services import conversation_store
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

    graph = build_onboarding_graph(turn_runner=run_onboarding_turn)
    result = await graph.ainvoke(
        {
            "message": message,
            "history": history,
            "vault_summary": summary,
            "possible_duplicates": duplicates,
            "profile_gaps": gaps,
            "already_finished": already_finished,
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
    await conversation_store.append_message(mongo_db, str(user.id), "assistant", turn["reply"])

    # Recompute completion from vault after upserts (not only the model flag).
    refreshed = await vault_summary(db, user.id)
    cats = {i["category"] for i in refreshed}
    vault_ready = {"project", "skill", "education"}.issubset(cats)

    return {
        "reply": turn["reply"],
        "items_created": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in created
        ],
        "items_updated": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in updated
        ],
        "onboarding_complete": turn["onboarding_complete"] or already_finished or vault_ready,
    }


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
