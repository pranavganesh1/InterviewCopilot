import uuid

import jwt
from fastapi import Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import IC_ACCESS_COOKIE, decode_token
from app.db.sqlalchemy import get_db
from app.models.user import User


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(IC_ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user_id = decode_token(token, "access")
        uid = uuid.UUID(user_id)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    user = await db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """403 unless the signed-in email is in ADMIN_EMAILS (M11 admin portal)."""
    allowed = get_settings().admin_email_set
    if user.email.lower() not in allowed:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_request_mongo(request: Request) -> AsyncIOMotorDatabase:
    """Reuse the lifespan Mongo DB handle — never open a new Motor client per request."""
    mongo_db = getattr(request.app.state, "mongo_db", None)
    if mongo_db is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    return mongo_db
