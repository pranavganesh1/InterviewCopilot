import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.models.vault import VaultItem

_PROJECT_DETAIL_KEYS = (
    "purpose",
    "technologies",
    "architecture",
    "contribution",
    "outcome",
    "features",
)


# Filler words ignored for equivalence (resume title punctuation variants).
_TITLE_FILLER = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "client",
        "for",
        "in",
        "of",
        "on",
        "the",
        "to",
        "with",
    }
)


def normalize_title(title: str) -> str:
    t = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    for suffix in (" system", " app", " application", " project"):
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
    tokens = [w for w in t.split() if w and w not in _TITLE_FILLER]
    return " ".join(tokens)


def titles_equivalent(a: str, b: str) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    return bool(na) and na == nb


def titles_similar(a: str, b: str) -> bool:
    """Near-duplicates that should be confirmed, not silently merged."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb or na == nb:
        return False
    if na in nb or nb in na:
        return True
    # High token overlap (e.g. internship title reorder / extra location).
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    inter = ta & tb
    return len(inter) >= 3 and len(inter) / min(len(ta), len(tb)) >= 0.75


def missing_project_details(details: dict | None) -> list[str]:
    d = details or {}
    return [k for k in _PROJECT_DETAIL_KEYS if not str(d.get(k) or "").strip()]


async def create_items(
    db: AsyncSession, user_id, items: list[ExtractedItem], source: str
) -> list[VaultItem]:
    rows = [
        VaultItem(
            user_id=user_id,
            category=i.category,
            title=i.title,
            details=i.details,
            source=source,
        )
        for i in items
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def list_items(db: AsyncSession, user_id) -> list[VaultItem]:
    result = await db.execute(
        select(VaultItem).where(VaultItem.user_id == user_id).order_by(VaultItem.created_at)
    )
    return list(result.scalars().all())


def _item_summary(item: VaultItem) -> dict:
    details = item.details or {}
    return {
        "id": str(item.id),
        "category": item.category,
        "title": item.title,
        "details": details,
        "source": item.source,
        "missing_details": (missing_project_details(details) if item.category == "project" else []),
    }


def _detail_richness(details: dict | None) -> int:
    return sum(1 for v in (details or {}).values() if str(v or "").strip())


def find_near_duplicates(items: list[VaultItem]) -> list[dict]:
    """Suspected duplicates for candidate review (never auto-deleted)."""
    pairs: list[dict] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            if a.category != b.category:
                continue
            equivalent = titles_equivalent(a.title, b.title)
            similar = titles_similar(a.title, b.title)
            if not equivalent and not similar:
                continue
            reason = (
                "Normalized titles match after ignoring punctuation and filler words."
                if equivalent
                else (
                    "Titles overlap strongly; they may be the same experience"
                    " with different wording."
                )
            )
            pairs.append(
                {
                    "category": a.category,
                    "reason": reason,
                    "match": "equivalent" if equivalent else "similar",
                    "a": {
                        "id": str(a.id),
                        "title": a.title,
                        "source": a.source,
                        "details": a.details or {},
                        "detail_count": _detail_richness(a.details),
                    },
                    "b": {
                        "id": str(b.id),
                        "title": b.title,
                        "source": b.source,
                        "details": b.details or {},
                        "detail_count": _detail_richness(b.details),
                    },
                }
            )
    return pairs


def suggest_keep_side(pair: dict) -> str:
    """Prefer the side with more detail fields; tie → longer title → 'a'."""
    a, b = pair["a"], pair["b"]
    if a.get("detail_count", 0) != b.get("detail_count", 0):
        return "a" if a.get("detail_count", 0) > b.get("detail_count", 0) else "b"
    if len(a.get("title") or "") != len(b.get("title") or ""):
        return "a" if len(a.get("title") or "") >= len(b.get("title") or "") else "b"
    return "a"


async def sync_resume_items(db: AsyncSession, user_id, items: list[ExtractedItem]) -> dict:
    """Incremental resume sync against the Profile Vault (source of truth).

    - Equivalent titles → skip (or flag enrichment; never silent overwrite)
    - Similar titles → uncertain match for review (no insert)
    - No match → create with source=resume
    Within-batch duplicates are collapsed first.
    """
    existing = await list_items(db, user_id)
    created: list[VaultItem] = []
    skipped: list[dict] = []
    enrichment: list[dict] = []
    uncertain: list[dict] = []
    failed: list[dict] = []
    seen_batch: set[tuple[str, str]] = set()

    for item in items:
        try:
            title = (item.title or "").strip()
            category = (item.category or "").strip().lower()
            if not title or not category:
                failed.append({"title": title or "(empty)", "reason": "missing_title_or_category"})
                continue
            batch_key = (category, normalize_title(title))
            if not batch_key[1]:
                failed.append({"title": title, "reason": "empty_normalized_title"})
                continue
            if batch_key in seen_batch:
                skipped.append(
                    {
                        "title": title,
                        "category": category,
                        "reason": "duplicate_in_extraction_batch",
                    }
                )
                continue
            seen_batch.add(batch_key)

            details = {
                str(k): str(v).strip()
                for k, v in (item.details or {}).items()
                if v is not None and str(v).strip()
            }

            same_cat = [row for row in existing if (row.category or "") == category]
            equiv = next(
                (row for row in same_cat if titles_equivalent(row.title, title)),
                None,
            )
            if equiv is not None:
                existing_details = dict(equiv.details or {})
                new_keys = [
                    k
                    for k, v in details.items()
                    if k not in existing_details or not str(existing_details.get(k) or "").strip()
                ]
                richer_values = [
                    k
                    for k, v in details.items()
                    if str(existing_details.get(k) or "").strip()
                    and str(existing_details.get(k) or "").strip() != v
                    and len(v) > len(str(existing_details.get(k) or ""))
                ]
                if new_keys or richer_values:
                    enrichment.append(
                        {
                            "title": title,
                            "category": category,
                            "existing_id": str(equiv.id),
                            "existing_title": equiv.title,
                            "existing_source": equiv.source,
                            "proposed_details": {k: details[k] for k in new_keys + richer_values},
                            "reason": "equivalent_record_exists_with_possible_new_details",
                        }
                    )
                skipped.append(
                    {
                        "title": title,
                        "category": category,
                        "reason": "equivalent_exists",
                        "existing_id": str(equiv.id),
                        "existing_title": equiv.title,
                    }
                )
                continue

            similar = next(
                (row for row in same_cat if titles_similar(row.title, title)),
                None,
            )
            if similar is not None:
                uncertain.append(
                    {
                        "title": title,
                        "category": category,
                        "existing_id": str(similar.id),
                        "existing_title": similar.title,
                        "existing_source": similar.source,
                        "reason": "similar_title_needs_review",
                        "proposed_details": details,
                    }
                )
                continue

            row = VaultItem(
                user_id=user_id,
                category=category,
                title=title,
                details=details,
                source="resume",
            )
            db.add(row)
            created.append(row)
            existing.append(row)
        except Exception as exc:  # noqa: BLE001 — isolate bad rows; continue sync
            failed.append(
                {
                    "title": getattr(item, "title", None) or "(unknown)",
                    "reason": f"persist_error:{type(exc).__name__}",
                }
            )

    if created:
        await db.commit()
        for row in created:
            await db.refresh(row)

    return {
        "items_created": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in created
        ],
        "items_skipped": skipped,
        "enrichment_candidates": enrichment,
        "uncertain_matches": uncertain,
        "items_failed": failed,
        "counts": {
            "created": len(created),
            "skipped": len(skipped),
            "enrichment_candidates": len(enrichment),
            "uncertain_matches": len(uncertain),
            "failed": len(failed),
        },
    }


async def apply_enrichment(
    db: AsyncSession,
    user_id,
    *,
    item_id: uuid.UUID,
    details: dict[str, str],
    only_fill_empty: bool = True,
) -> VaultItem | None:
    """Apply candidate-approved enrichment without wiping existing values."""
    item = await db.get(VaultItem, item_id)
    if item is None or item.user_id != user_id:
        return None
    merged = dict(item.details or {})
    changed = False
    for key, value in (details or {}).items():
        text = str(value).strip() if value is not None else ""
        if not text:
            continue
        current = str(merged.get(key) or "").strip()
        if only_fill_empty and current:
            continue
        if current != text:
            merged[key] = text
            changed = True
    if changed:
        item.details = merged
        await db.commit()
        await db.refresh(item)
    return item


async def resolve_duplicate_pair(
    db: AsyncSession,
    user_id,
    *,
    keep_id: uuid.UUID,
    discard_id: uuid.UUID,
    merge_details: bool = True,
) -> dict | None:
    """Candidate-approved cleanup: merge into keep, then delete discard (same user only)."""
    if keep_id == discard_id:
        return None
    keep = await db.get(VaultItem, keep_id)
    discard = await db.get(VaultItem, discard_id)
    if keep is None or discard is None or keep.user_id != user_id or discard.user_id != user_id:
        return None
    if keep.category != discard.category:
        return None
    if merge_details:
        merged = dict(keep.details or {})
        for key, value in (discard.details or {}).items():
            text = str(value or "").strip()
            if not text:
                continue
            current = str(merged.get(key) or "").strip()
            if not current or len(text) > len(current):
                merged[key] = text
        keep.details = merged
        if len(discard.title or "") > len(keep.title or ""):
            keep.title = discard.title
    await db.delete(discard)
    await db.commit()
    await db.refresh(keep)
    return _item_summary(keep)


async def list_resume_sourced_items(db: AsyncSession, user_id) -> list[VaultItem]:
    items = await list_items(db, user_id)
    return [i for i in items if (i.source or "").strip().lower() == "resume"]


async def reset_resume_sourced_items(db: AsyncSession, user_id) -> dict:
    """Delete only this user's source=resume vault rows. Never touches account/interview data."""
    rows = await list_resume_sourced_items(db, user_id)
    removed = [
        {"id": str(r.id), "category": r.category, "title": r.title, "source": r.source}
        for r in rows
    ]
    for row in rows:
        await db.delete(row)
    if rows:
        await db.commit()
    return {
        "removed_count": len(removed),
        "removed": removed,
        "scope": "source=resume only for authenticated user",
        "preserved": [
            "account/auth",
            "manual vault items",
            "onboarding_chat vault items",
            "interview sessions",
            "answers",
            "feedback reports",
            "conversations",
        ],
    }


async def vault_summary(db: AsyncSession, user_id) -> list[dict]:
    items = await list_items(db, user_id)
    return [_item_summary(i) for i in items]


async def upsert_extracted_items(
    db: AsyncSession, user_id, items: list[ExtractedItem], source: str
) -> tuple[list[VaultItem], list[VaultItem]]:
    """Create new vault rows or merge details into equivalent titles.

    Near-duplicates (similar but not equivalent) are left alone so the coach
    can ask the candidate to confirm before merging.
    """
    existing = await list_items(db, user_id)
    created: list[VaultItem] = []
    updated: list[VaultItem] = []

    for item in items:
        title = (item.title or "").strip()
        if not title:
            continue
        details = {
            str(k): str(v).strip()
            for k, v in (item.details or {}).items()
            if v is not None and str(v).strip()
        }
        match = next(
            (
                row
                for row in existing
                if row.category == item.category and titles_equivalent(row.title, title)
            ),
            None,
        )
        if match is None:
            row = VaultItem(
                user_id=user_id,
                category=item.category,
                title=title,
                details=details,
                source=source,
            )
            db.add(row)
            created.append(row)
            existing.append(row)
            continue

        merged = dict(match.details or {})
        changed = False
        for key, value in details.items():
            if merged.get(key) != value:
                merged[key] = value
                changed = True
        if len(title) > len(match.title or ""):
            match.title = title
            changed = True
        if changed:
            match.details = merged
            updated.append(match)

    if created or updated:
        await db.commit()
        for row in created + updated:
            await db.refresh(row)
    return created, updated


async def update_item(
    db: AsyncSession,
    user_id,
    item_id: uuid.UUID,
    *,
    title: str | None = None,
    details: dict[str, str] | None = None,
) -> VaultItem | None:
    item = await db.get(VaultItem, item_id)
    if item is None or item.user_id != user_id:
        return None
    if title is not None:
        cleaned = title.strip()
        if cleaned:
            item.title = cleaned
    if details is not None:
        merged = dict(item.details or {})
        for key, value in details.items():
            text = str(value).strip() if value is not None else ""
            if text:
                merged[key] = text
            elif key in merged:
                del merged[key]
        item.details = merged
    await db.commit()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, user_id, item_id: uuid.UUID) -> bool:
    item = await db.get(VaultItem, item_id)
    if item is None or item.user_id != user_id:
        return False
    await db.delete(item)
    await db.commit()
    return True


async def vault_probe_ready(db: AsyncSession, user_id) -> bool:
    """True when the vault has at least one project, skill, or internship."""
    items = await list_items(db, user_id)
    return any(
        (item.category or "").lower() in ("project", "skill", "internship") for item in items
    )


# Fingerprints for idempotent welcome detection (must appear in coach copy).
RESUME_WELCOME_MARKER = "I've gone through your resume"
# Legacy marker still recognized so older threads stay idempotent.
_LEGACY_RESUME_WELCOME_MARKER = "I've reviewed your resume"
RESUME_UPLOAD_SUCCESS_MARKER = "I've gone through your resume"
PROFILE_VERIFY_MARKER = "make sure everything looks right"


def build_verify_first_welcome(
    *,
    sync_result: dict | None = None,
    item_count: int = 0,
    mode: str = "resume",
) -> str:
    """Coach-style opener — outcome-aware, no system/pipeline jargon, no auto project pick."""
    sync = sync_result if isinstance(sync_result, dict) else {}
    counts = sync.get("counts") if isinstance(sync.get("counts"), dict) else {}
    created = int(counts.get("created") or len(sync.get("items_created") or []) or 0)
    skipped = int(counts.get("skipped") or 0)
    failed = int(counts.get("failed") or len(sync.get("items_failed") or []) or 0)

    if mode == "new_chat":
        return "\n".join(
            [
                "Hey! Ready when you are.",
                "",
                "We can work from the profile we already have — education, experience, "
                "projects and skills.",
                "",
                f"Before we get started, I'd like to {PROFILE_VERIFY_MARKER}.",
                "",
                "Is your education, work experience, projects and skills information correct?",
                "",
                "Once we've reviewed that, tell me what kind of role you're aiming for. "
                "We'll build your preparation around your goals and experience.",
            ]
        )

    if failed and created == 0 and skipped == 0 and item_count == 0:
        return "\n".join(
            [
                "Hey — thanks for sharing your resume.",
                "",
                "I wasn't able to read the details clearly this time, so I haven't "
                "updated your profile yet.",
                "",
                "Could you try uploading again, or tell me a little about your "
                "background so we can get started?",
            ]
        )

    if created > 0:
        body = (
            f"Hey! Welcome back.\n\n"
            f"{RESUME_WELCOME_MARKER} and updated your profile with the information "
            f"I could identify."
        )
    elif skipped > 0 or item_count > 0:
        body = (
            f"Hey! Welcome back.\n\n"
            f"{RESUME_WELCOME_MARKER} again. Your profile already covered most of this, "
            f"so I kept things consistent rather than adding repeats."
        )
    else:
        body = (
            f"Hey! Welcome back.\n\n"
            f"{RESUME_WELCOME_MARKER}. I didn't find much new detail to add yet — "
            f"we can fill gaps as we chat."
        )

    if failed and created > 0:
        body += (
            "\n\nA few pieces didn't come through cleanly; we can fix those together as we review."
        )

    return "\n".join(
        [
            body,
            "",
            f"Before we get started, I'd like to {PROFILE_VERIFY_MARKER}.",
            "",
            "Is your education, work experience, projects and skills information correct?",
            "",
            "Once we've reviewed that, tell me what kind of role you're aiming for. "
            "We'll build your preparation around your goals and experience.",
        ]
    )


def build_resume_sync_welcome(sync_result: dict | None, items: list) -> str:
    """Welcome grounded in the real upload/sync result — never invents extraction success."""
    return build_verify_first_welcome(
        sync_result=sync_result, item_count=len(items or []), mode="resume"
    )


def build_profile_review_message(items: list[VaultItem]) -> str:
    """Coach-style verify-first welcome — never auto-selects a project."""
    if not items:
        return "\n".join(
            [
                "Hey! Good to meet you.",
                "",
                "I don't have your background yet. Upload a resume or tell me what "
                "you're interested in — we'll shape your prep from there. "
                "No degree or project required to start.",
            ]
        )

    lines = [
        "Hey! Welcome back.",
        "",
        f"{RESUME_WELCOME_MARKER} and I have a profile ready for us to work from.",
        "",
        f"Before we get started, I'd like to {PROFILE_VERIFY_MARKER}.",
        "",
        "Is your education, work experience, projects and skills information correct?",
        "",
        "Once we've reviewed that, tell me what kind of role you're aiming for. "
        "We'll build your preparation around your goals and experience.",
    ]
    near = find_near_duplicates(items)
    if near:
        pair = near[0]
        lines.extend(
            [
                "",
                f"One quick check: “{pair['a']['title']}” and “{pair['b']['title']}” "
                "look similar — should we keep both, or is that the same item?",
            ]
        )
    return "\n".join(lines)


def message_looks_like_resume_welcome(content: str) -> bool:
    text = content or ""
    return (
        RESUME_WELCOME_MARKER in text
        or _LEGACY_RESUME_WELCOME_MARKER in text
        or PROFILE_VERIFY_MARKER in text
        or text.startswith("Hey! Welcome back.")
        or text.startswith("Hey! Ready when you are.")
        or text.startswith("Your resume has been uploaded successfully")
        or text.startswith("Your new conversation is ready!")
        or text.startswith("Welcome back — I already pulled")
    )
