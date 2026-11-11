from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.preparation_goals import normalize_preferences

CONVERSATIONS = "onboarding_conversations"


async def append_message(
    mongo_db: AsyncIOMotorDatabase, user_id: str, role: str, content: str
) -> None:
    now = datetime.now(UTC).isoformat()
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$push": {"messages": {"role": role, "content": content, "created_at": now}},
            "$set": {"updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def get_messages(mongo_db: AsyncIOMotorDatabase, user_id: str, limit: int = 50) -> list[dict]:
    doc = await mongo_db[CONVERSATIONS].find_one({"user_id": user_id})
    if not doc:
        return []
    return doc.get("messages", [])[-limit:]


async def get_preparation_preferences(
    mongo_db: AsyncIOMotorDatabase, user_id: str
) -> dict:
    doc = await mongo_db[CONVERSATIONS].find_one(
        {"user_id": user_id}, {"preparation_preferences": 1}
    )
    return normalize_preferences((doc or {}).get("preparation_preferences"))


async def set_preparation_preferences(
    mongo_db: AsyncIOMotorDatabase, user_id: str, preferences: dict
) -> dict:
    prefs = normalize_preferences(preferences)
    now = datetime.now(UTC).isoformat()
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "preparation_preferences": prefs,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now, "messages": []},
        },
        upsert=True,
    )
    return prefs


async def get_conversation_mode(mongo_db: AsyncIOMotorDatabase, user_id: str) -> str | None:
    doc = await mongo_db[CONVERSATIONS].find_one({"user_id": user_id}, {"conversation_mode": 1})
    mode = (doc or {}).get("conversation_mode")
    return str(mode) if mode else None


async def set_conversation_mode(
    mongo_db: AsyncIOMotorDatabase, user_id: str, mode: str | None
) -> None:
    now = datetime.now(UTC).isoformat()
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$set": {"conversation_mode": mode, "updated_at": now},
            "$setOnInsert": {"created_at": now, "messages": []},
        },
        upsert=True,
    )


async def get_profile_review(mongo_db: AsyncIOMotorDatabase, user_id: str) -> dict | None:
    doc = await mongo_db[CONVERSATIONS].find_one(
        {"user_id": user_id}, {"profile_review": 1}
    )
    review = (doc or {}).get("profile_review")
    return review if isinstance(review, dict) else None


async def set_profile_review(
    mongo_db: AsyncIOMotorDatabase, user_id: str, review: dict
) -> dict:
    now = datetime.now(UTC).isoformat()
    payload = dict(review or {})
    payload["updated_at"] = now
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$set": {"profile_review": payload, "updated_at": now},
            "$setOnInsert": {"created_at": now, "messages": []},
        },
        upsert=True,
    )
    return payload
