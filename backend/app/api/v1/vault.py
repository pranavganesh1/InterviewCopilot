from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services.vault_service import create_items, list_items

router = APIRouter(prefix="/vault", tags=["vault"])


class ManualItem(BaseModel):
    category: str
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


@router.get("/items")
async def get_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await list_items(db, user.id)
    return [
        {
            "id": str(i.id),
            "category": i.category,
            "title": i.title,
            "details": i.details,
            "source": i.source,
        }
        for i in items
    ]


@router.post("/items")
async def add_item(
    body: ManualItem, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if body.category not in ExtractedItem.model_fields["category"].annotation.__args__:
        raise HTTPException(status_code=422, detail=f"Unknown category: {body.category}")
    created = await create_items(db, user.id, [ExtractedItem(**body.model_dump())], "manual")
    i = created[0]
    return {"id": str(i.id), "category": i.category, "title": i.title}
