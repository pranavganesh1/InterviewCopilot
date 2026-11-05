import uuid

import jwt
from fastapi import Depends, HTTPException, Request
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
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """403 unless the signed-in email is in ADMIN_EMAILS (M11 admin portal)."""
    allowed = {e.strip().lower() for e in get_settings().admin_emails.split(",") if e.strip()}
    if user.email.lower() not in allowed:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Admin access required")
    return user
