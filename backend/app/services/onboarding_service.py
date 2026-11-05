from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem, build_onboarding_graph
from app.models.user import User
from app.services import conversation_store
from app.services.vault_service import create_items, vault_summary


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
    history = await conversation_store.get_messages(mongo_db, str(user.id), limit=20)
    summary = await vault_summary(db, user.id)

    graph = build_onboarding_graph(turn_runner=run_onboarding_turn)
    result = await graph.ainvoke(
        {
            "message": message,
            "history": history,
            "vault_summary": summary,
            "already_finished": already_finished,
            "meta": {"user_id": str(user.id)},
        }
    )
    turn = result["turn"]

    created = await create_items(
        db, user.id, [ExtractedItem(**i) for i in turn["extracted_items"]], "onboarding_chat"
    )
    await conversation_store.append_message(mongo_db, str(user.id), "assistant", turn["reply"])
    return {
        "reply": turn["reply"],
        "items_created": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in created
        ],
        "onboarding_complete": turn["onboarding_complete"] or already_finished,
    }
