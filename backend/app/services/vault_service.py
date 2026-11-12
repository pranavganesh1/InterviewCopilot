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


def normalize_title(title: str) -> str:
    t = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    for suffix in (" system", " app", " application", " project"):
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
    return t


def titles_equivalent(a: str, b: str) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    return bool(na) and na == nb


def titles_similar(a: str, b: str) -> bool:
    """Near-duplicates that should be confirmed, not silently merged."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb or na == nb:
        return False
    return na in nb or nb in na


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
        "missing_details": (
            missing_project_details(details) if item.category == "project" else []
        ),
    }


def find_near_duplicates(items: list[VaultItem]) -> list[dict]:
    pairs: list[dict] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            if a.category != b.category:
                continue
            if titles_similar(a.title, b.title):
                pairs.append(
                    {
                        "category": a.category,
                        "a": {"id": str(a.id), "title": a.title},
                        "b": {"id": str(b.id), "title": b.title},
                    }
                )
    return pairs


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


# Fingerprint used to avoid duplicate automatic welcome messages.
RESUME_WELCOME_MARKER = "I've reviewed your resume"


def build_profile_review_message(items: list[VaultItem]) -> str:
    """Field-aware welcome — 1–2 hooks from the resume, never a CS-only assumption."""
    from app.services.preparation_goals import infer_candidate_background

    if not items:
        return (
            "Hey! 👋 I don't have your background yet. "
            "Upload a resume or tell me what you're interested in — "
            "we'll shape your prep from there. No degree or project required to start."
        )

    summary = [
        {
            "category": item.category,
            "title": item.title,
            "details": item.details or {},
        }
        for item in items
    ]
    bg = infer_candidate_background(summary)
    field = bg["field_family"]
    education = bg["education_titles"]
    skills = bg["skill_titles"]
    projects = bg["project_titles"]
    internships = bg["internship_titles"]

    if field == "commerce" and education:
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER}. I noticed your background in "
            f"{education[0]}. We can explore finance, accounting, business analytics, "
            "or roles connected to your experience."
        )
    elif field == "physics" and (education or projects):
        hook = education[0] if education else f"your “{projects[0]}” work"
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER}. I see {hook}. "
            "Your analytical background could fit research, technical roles, "
            "or broader interview prep."
        )
    elif field in ("life_sciences", "mathematics", "arts", "engineering") and education:
        hook = ""
        if projects:
            hook = f" Your “{projects[0]}” work stood out."
        elif skills:
            hook = f" I also noticed {skills[0]} in your profile."
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER}. I noticed your background in "
            f"{education[0]}.{hook} We can explore roles and prep paths that match "
            "your interests — not only software."
        )
    elif field == "computer_science" and (skills or projects):
        if projects and skills:
            opener = (
                f"Hey! 👋 {RESUME_WELCOME_MARKER}. I noticed {skills[0]}"
                + (f" and your “{projects[0]}” project" if projects else "")
                + ". We can explore technical skills, projects, or career goals next."
            )
        elif projects:
            opener = (
                f"Hey! 👋 {RESUME_WELCOME_MARKER}. Your “{projects[0]}” project looks "
                "like a strong interview story — happy to dig in when you're ready."
            )
        else:
            opener = (
                f"Hey! 👋 {RESUME_WELCOME_MARKER}. I noticed {skills[0]} in your profile. "
                "We can practise skills, talk goals, or explore projects."
            )
    elif projects:
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER}. Your “{projects[0]}” work stood out — "
            "we can build interview prep around that or explore other goals."
        )
    elif internships:
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER}. I noticed your {internships[0]} experience. "
            "We can turn that into interview stories or explore new directions."
        )
    elif skills:
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER}. I noticed {skills[0]} in your profile. "
            "We can practise that skill or explore what you'd like to prepare for."
        )
    elif education:
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER}. I noticed your background in {education[0]}. "
            "What are you currently interested in exploring?"
        )
    else:
        opener = (
            f"Hey! 👋 {RESUME_WELCOME_MARKER} and saved a few notes. "
            "Tell me what you'd like to work toward — any direction is welcome."
        )

    lines = [
        opener,
        "",
        "What would you like to work on first? Pick a starter below, choose a prep focus, "
        "or just type — you can skip anything that doesn't apply.",
    ]

    near = find_near_duplicates(items)
    if near:
        pair = near[0]
        lines.extend(
            [
                "",
                f"Quick check: “{pair['a']['title']}” and “{pair['b']['title']}” look similar — "
                "same item, or keep both?",
            ]
        )
    return "\n".join(lines)


def message_looks_like_resume_welcome(content: str) -> bool:
    text = content or ""
    return RESUME_WELCOME_MARKER in text or text.startswith("Welcome back — I already pulled")
