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


EMPTY_COACH_CONTEXT: dict = {
    "background": {},
    "confirmed_facts": [],
    "current_topic": None,
    "asked_questions": [],
    "skipped_categories": [],
    "not_applicable_categories": [],
    "answers_received": [],
    "proceed_to_goals": False,
}


def normalize_coach_context(raw: dict | None) -> dict:
    base = {
        **EMPTY_COACH_CONTEXT,
        "background": {},
        "confirmed_facts": [],
        "asked_questions": [],
        "skipped_categories": [],
        "not_applicable_categories": [],
        "answers_received": [],
    }
    if not isinstance(raw, dict):
        return base

    def _str_list(key: str, limit: int = 40) -> list[str]:
        vals = raw.get(key) or []
        if not isinstance(vals, list):
            return []
        out: list[str] = []
        for v in vals:
            s = str(v).strip()
            if s and s not in out:
                out.append(s[:240])
        return out[:limit]

    bg = raw.get("background") if isinstance(raw.get("background"), dict) else {}
    base.update(
        {
            "background": bg,
            "confirmed_facts": _str_list("confirmed_facts"),
            "current_topic": (
                str(raw["current_topic"]).strip()[:120]
                if raw.get("current_topic")
                else None
            ),
            "asked_questions": _str_list("asked_questions", 60),
            "skipped_categories": _str_list("skipped_categories", 20),
            "not_applicable_categories": _str_list("not_applicable_categories", 20),
            "answers_received": _str_list("answers_received", 40),
            "proceed_to_goals": bool(raw.get("proceed_to_goals")),
        }
    )
    return base


async def get_coach_context(mongo_db: AsyncIOMotorDatabase, user_id: str) -> dict:
    doc = await mongo_db[CONVERSATIONS].find_one(
        {"user_id": user_id}, {"coach_context": 1}
    )
    return normalize_coach_context((doc or {}).get("coach_context"))


async def set_coach_context(
    mongo_db: AsyncIOMotorDatabase, user_id: str, context: dict
) -> dict:
    payload = normalize_coach_context(context)
    now = datetime.now(UTC).isoformat()
    payload["updated_at"] = now
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$set": {"coach_context": payload, "updated_at": now},
            "$setOnInsert": {"created_at": now, "messages": []},
        },
        upsert=True,
    )
    return payload


async def merge_coach_context(
    mongo_db: AsyncIOMotorDatabase, user_id: str, patch: dict
) -> dict:
    current = await get_coach_context(mongo_db, user_id)
    merged = {**current, **{k: v for k, v in (patch or {}).items() if v is not None}}
    for key in (
        "confirmed_facts",
        "asked_questions",
        "skipped_categories",
        "not_applicable_categories",
        "answers_received",
    ):
        if key in patch and isinstance(patch[key], list):
            merged[key] = normalize_coach_context({key: patch[key]})[key]
    if "background" in patch and isinstance(patch["background"], dict):
        merged["background"] = {**(current.get("background") or {}), **patch["background"]}
    return await set_coach_context(mongo_db, user_id, merged)


async def get_idempotent_chat_reply(
    mongo_db: AsyncIOMotorDatabase, user_id: str, message_id: str
) -> dict | None:
    """Return a prior chat response body for this client message id, if any."""
    mid = (message_id or "").strip()[:80]
    if not mid:
        return None
    doc = await mongo_db[CONVERSATIONS].find_one(
        {"user_id": user_id}, {"chat_idempotency": 1}
    )
    bucket = (doc or {}).get("chat_idempotency") or {}
    cached = bucket.get(mid)
    return cached if isinstance(cached, dict) else None


async def save_idempotent_chat_reply(
    mongo_db: AsyncIOMotorDatabase, user_id: str, message_id: str, payload: dict
) -> None:
    mid = (message_id or "").strip()[:80]
    if not mid:
        return
    now = datetime.now(UTC).isoformat()
    # Keep a small window of recent ids so the doc stays bounded.
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$set": {
                f"chat_idempotency.{mid}": payload,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now, "messages": []},
        },
        upsert=True,
    )


async def try_acquire_chat_lock(
    mongo_db: AsyncIOMotorDatabase, user_id: str, message_id: str
) -> bool:
    """Acquire a short chat lock. False if another request holds it."""
    mid = (message_id or "").strip()[:80] or f"anon-{datetime.now(UTC).timestamp()}"
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    stale_before = datetime.fromtimestamp(now.timestamp() - 45, tz=UTC).isoformat()
    # Ensure the conversation doc exists without clobbering an active lock.
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"created_at": now_iso, "messages": [], "user_id": user_id}},
        upsert=True,
    )
    result = await mongo_db[CONVERSATIONS].update_one(
        {
            "user_id": user_id,
            "$or": [
                {"chat_lock": {"$exists": False}},
                {"chat_lock": None},
                {"chat_lock.updated_at": {"$lt": stale_before}},
            ],
        },
        {
            "$set": {
                "chat_lock": {"message_id": mid, "updated_at": now_iso},
                "updated_at": now_iso,
            }
        },
    )
    return result.modified_count == 1


async def release_chat_lock(
    mongo_db: AsyncIOMotorDatabase, user_id: str, message_id: str | None = None
) -> None:
    mid = (message_id or "").strip()[:80] if message_id else None
    filt: dict = {"user_id": user_id}
    if mid:
        filt["chat_lock.message_id"] = mid
    await mongo_db[CONVERSATIONS].update_one(filt, {"$unset": {"chat_lock": ""}})


async def get_start_offer_shown(mongo_db: AsyncIOMotorDatabase, user_id: str) -> bool:
    doc = await mongo_db[CONVERSATIONS].find_one(
        {"user_id": user_id}, {"start_interview_offer_shown": 1}
    )
    return bool((doc or {}).get("start_interview_offer_shown"))


async def mark_start_offer_shown(mongo_db: AsyncIOMotorDatabase, user_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$set": {"start_interview_offer_shown": True, "updated_at": now},
            "$setOnInsert": {"created_at": now, "messages": []},
        },
        upsert=True,
    )
