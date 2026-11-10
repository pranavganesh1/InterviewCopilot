from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.models.vault import VaultItem


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


async def vault_summary(db: AsyncSession, user_id) -> list[dict]:
    return [{"category": i.category, "title": i.title} for i in await list_items(db, user_id)]


async def vault_probe_ready(db: AsyncSession, user_id) -> bool:
    """True when the vault has at least one project, skill, or internship."""
    items = await list_items(db, user_id)
    return any(
        (item.category or "").lower() in ("project", "skill", "internship") for item in items
    )
