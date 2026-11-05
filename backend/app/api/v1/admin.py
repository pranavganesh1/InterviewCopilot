import uuid

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.mongo import get_mongo_db
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
async def overview(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    return await admin_service.overview(db, mongo)


@router.get("/users")
async def users(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    return await admin_service.users_rollup(db, mongo)


@router.get("/users/{user_id}")
async def user_detail(
    user_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    result = await admin_service.user_detail(db, mongo, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result
