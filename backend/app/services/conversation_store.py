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
    base = {**EMPTY_COACH_CONTEXT, "background": {}, "confirmed_facts": [], "asked_questions": [], "skipped_categories": [], "not_applicable_categories": [], "answers_received": []}
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
