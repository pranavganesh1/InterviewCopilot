from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    IC_ACCESS_COOKIE,
    IC_REFRESH_COOKIE,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import profile_service

router = APIRouter(prefix="/auth", tags=["auth"])


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    professional_title: str | None = Field(default=None, max_length=255)
    introduction: str | None = Field(default=None, max_length=4000)
    education: str | None = Field(default=None, max_length=4000)
    picture_url: str | None = Field(default=None, max_length=1024)
    skills: list[str] | None = None


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    secure = settings.app_env != "local"
    response.set_cookie(
        IC_ACCESS_COOKIE,
        access,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        IC_REFRESH_COOKIE,
        refresh,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


async def _upsert_user(db: AsyncSession, userinfo: dict) -> User:
    result = await db.execute(select(User).where(User.google_sub == userinfo["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            google_sub=userinfo["sub"],
            email=userinfo.get("email", ""),
            name=userinfo.get("name", ""),
            picture_url=userinfo.get("picture"),
        )
        db.add(user)
    else:
        # Keep editable profile fields; only refresh email from Google.
        user.email = userinfo.get("email", user.email)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/google/url")
async def google_auth_url(request: Request):
    # 302 straight to Google consent. Browsers and the future frontend both
    # just follow it (state is stored in the session cookie by authlib).
    return await request.app.state.oauth.google.authorize_redirect(
        request, get_settings().google_redirect_uri
    )


@router.get("/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    token = await request.app.state.oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=401, detail="Google sign-in failed")
    user = await _upsert_user(db, userinfo)
    # Cookies ride on the redirect; the SPA then bootstraps via /auth/me.
    response = RedirectResponse(url=get_settings().frontend_url, status_code=303)
    _set_auth_cookies(
        response, create_access_token(str(user.id)), create_refresh_token(str(user.id))
    )
    return response


@router.post("/refresh")
async def refresh(request: Request):
    token = request.cookies.get(IC_REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        user_id = decode_token(token, "refresh")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None
    response = Response()
    _set_auth_cookies(response, create_access_token(user_id), create_refresh_token(user_id))
    return response


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(IC_ACCESS_COOKIE)
    response.delete_cookie(IC_REFRESH_COOKIE)
    return {"status": "ok"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return profile_service.user_dict(user)


@router.patch("/me")
async def update_me(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await profile_service.update_profile(
            db, user, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        if str(exc) == "skills_must_be_list":
            raise HTTPException(status_code=422, detail="skills must be a list") from None
        raise
