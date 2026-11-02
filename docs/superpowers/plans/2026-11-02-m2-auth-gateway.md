# InterviewCopilot M2 — Auth & LLM Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Google OAuth sign-in works end-to-end in the browser (backend-issued JWT cookie pair), and the LLM gateway completes a real round-trip through LiteLLM with the call logged to MongoDB.

**Architecture:** SQLAlchemy 2 async + Alembic (async template) own Postgres state. PyJWT issues access/refresh pairs in httpOnly SameSite cookies. Authlib drives the Google OIDC dance with state stored in Starlette SessionMiddleware. Motor writes `llm_call_logs` to MongoDB. The gateway client speaks OpenAI-compatible chat completions to the LiteLLM proxy on `localhost:4000`.

**Tech Stack:** SQLAlchemy 2 + asyncpg + Alembic, PyJWT, Authlib, Motor, httpx, mongomock-motor (dev).

**Spec:** `docs/superpowers/specs/2026-11-02-interviewcopilot-v1-build-design.md` (M2 row of §14)

## Global Constraints

- Same as M1 (Python 3.13 + uv, Git Bash on Windows, conventional commits, secrets only in `.env`).
- Backend config reads the **repo-root** `.env` (single source shared with docker-compose) via an absolute path — removes M1's CWD dependence.
- Integration tests rely on the dockerized stack running (same prereq as M1 acceptance).
- Dev-only endpoints are gated on `APP_ENV=local`.

---

### Task 1: Settings expansion + new dependencies + .env.example

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/pyproject.toml` (dependencies)
- Modify: `.env.example`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings` fields used by every later task — `database_url`, `mongo_url`, `mongo_db`, `jwt_secret`, `jwt_algorithm`, `access_token_ttl_minutes`, `refresh_token_ttl_days`, `google_client_id`, `google_client_secret`, `google_redirect_uri`, `frontend_url`, `litellm_url`, `litellm_master_key`; plus `PROJECT_ROOT` path constant. `.env.example` gains `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `FRONTEND_URL`, `MONGO_DB`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_settings.py`:

```python
from app.core.config import PROJECT_ROOT, get_settings


def test_settings_load_from_root_env():
    settings = get_settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.mongo_db == "interviewcopilot"
    assert settings.litellm_url == "http://localhost:4000"
    assert PROJECT_ROOT.name == "InterviewCopilot"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_settings.py -v`
Expected: FAIL — `ImportError: cannot import name 'PROJECT_ROOT'`.

- [ ] **Step 3: Implement**

Update deps in `backend/pyproject.toml` `[project].dependencies` (append):

```toml
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "motor>=3.6",
    "pyjwt>=2.10",
    "authlib>=1.4",
```

Add to `[dependency-groups].dev`:

```toml
    "mongomock-motor>=0.0.35",
    "aiosqlite>=0.20",
```

Replace `backend/app/core/config.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[3] is the repo root (shared .env with docker-compose)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), extra="ignore")

    app_name: str = "InterviewCopilot"
    app_env: str = "local"  # local | staging | prod
    log_level: str = "INFO"

    # Postgres
    database_url: str = (
        "postgresql+asyncpg://interview:interview@localhost:5432/interviewcopilot"
    )

    # MongoDB
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "interviewcopilot"

    # Auth (backend-issued JWT cookie pair)
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    frontend_url: str = "http://localhost:5173"

    # LLM gateway (LiteLLM proxy)
    litellm_url: str = "http://localhost:4000"
    litellm_master_key: str = "sk-local-master"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Append to `.env.example` (repo root) after the `# LLM gateway` block:

```bash

# Auth (backend-issued JWTs + Google OAuth)
JWT_SECRET=change-me-to-a-long-random-string
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
FRONTEND_URL=http://localhost:5173
MONGO_DB=interviewcopilot
```

Run: `cd .. && cp .env.example .env` (refresh the local `.env` with the new keys).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv sync && uv run pytest tests/test_settings.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend .env.example
git commit -m "feat(backend): settings for db/auth/gateway + dependencies"
```

---

### Task 2: SQLAlchemy engine, users model, Alembic migration

**Files:**
- Create: `backend/app/db/__init__.py` (empty), `backend/app/db/sqlalchemy.py`, `backend/app/db/mongo.py`
- Create: `backend/app/models/__init__.py` (empty), `backend/app/models/user.py`
- Create: `backend/alembic/` (async template), `backend/alembic.ini`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `Settings.database_url`, `Settings.mongo_url`, `Settings.mongo_db`.
- Produces: `app.db.sqlalchemy.engine`, `app.db.sqlalchemy.SessionFactory` (async_sessionmaker), `app.db.sqlalchemy.get_db()` (FastAPI dependency yielding `AsyncSession`); `app.db.mongo.get_mongo_client()` (cached `AsyncIOMotorClient`); `app.models.user.User` with fields `id: uuid.UUID`, `google_sub: str`, `email: str`, `name: str`, `picture_url: str | None`, `created_at`, `updated_at`; `app.models.user.Base` (DeclarativeBase) for all future tables. Alembic CLI runnable via `uv run alembic ...` from `backend/`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_models.py`:

```python
import uuid

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.user import User


@pytest.mark.asyncio
async def test_user_roundtrip():
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email="t@example.com", name="T")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.id is not None
        assert user.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Implement**

Create `backend/app/db/sqlalchemy.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with SessionFactory() as session:
        yield session
```

Create `backend/app/db/mongo.py`:

```python
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings


@lru_cache
def get_mongo_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(get_settings().mongo_url)


def get_mongo_db() -> AsyncIOMotorDatabase:
    return get_mongo_client()[get_settings().mongo_db]
```

Create `backend/app/models/user.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    picture_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Initialize Alembic (async template) and wire it to settings:

```bash
cd backend && uv run alembic init -t async alembic
```

In `backend/alembic/env.py`, add at the top of the imports section:

```python
from app.core.config import get_settings
from app.models.user import Base
```

and set (inside `run_migrations_online` context setup, replacing the existing
`config.get_main_option("sqlalchemy.url")` usage):

```python
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

Generate and apply the first migration:

```bash
cd backend && uv run alembic revision --autogenerate -m "create users table" && uv run alembic upgrade head
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: PASS (1 passed).

Verify table exists: `docker compose exec -T postgres psql -U interview -d interviewcopilot -c "\dt"` → lists `users` and `alembic_version`.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): async SQLAlchemy engine, users model, alembic migration"
```

---

### Task 3: JWT core

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Consumes: `Settings.jwt_secret`, `jwt_algorithm`, `access_token_ttl_minutes`, `refresh_token_ttl_days`.
- Produces: `create_access_token(user_id: str, ttl_seconds: int | None = None) -> str`; `create_refresh_token(user_id: str, ttl_seconds: int | None = None) -> str`; `decode_token(token: str, expected_type: str) -> str` — returns subject or raises `jwt.PyJWTError`. Cookie names `IC_ACCESS_COOKIE = "ic_access"`, `IC_REFRESH_COOKIE = "ic_refresh"`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_security.py`:

```python
import jwt
import pytest

from app.core.security import create_access_token, create_refresh_token, decode_token


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    assert decode_token(token, "access") == "user-123"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-123")
    assert decode_token(token, "refresh") == "user-123"


def test_wrong_type_rejected():
    token = create_refresh_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, "access")


def test_expired_token_rejected():
    token = create_access_token("user-123", ttl_seconds=-10)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, "access")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_security.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.security'`.

- [ ] **Step 3: Implement**

Create `backend/app/core/security.py`:

```python
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

IC_ACCESS_COOKIE = "ic_access"
IC_REFRESH_COOKIE = "ic_refresh"


def _create_token(subject: str, token_type: str, ttl_seconds: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, ttl_seconds: int | None = None) -> str:
    settings = get_settings()
    ttl = ttl_seconds or settings.access_token_ttl_minutes * 60
    return _create_token(user_id, "access", ttl)


def create_refresh_token(user_id: str, ttl_seconds: int | None = None) -> str:
    settings = get_settings()
    ttl = ttl_seconds or settings.refresh_token_ttl_days * 24 * 3600
    return _create_token(user_id, "refresh", ttl)


def decode_token(token: str, expected_type: str) -> str:
    """Return the token subject if valid and of expected_type; raise jwt.PyJWTError otherwise."""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return str(payload["sub"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_security.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): JWT access/refresh token core"
```

---

### Task 4: Google OAuth routes, cookies, current-user dependency

**Files:**
- Create: `backend/app/api/__init__.py` (empty), `backend/app/api/v1/__init__.py` (empty), `backend/app/api/deps.py`, `backend/app/api/v1/auth.py`
- Modify: `backend/app/main.py` (routers, SessionMiddleware, oauth state, lifespan)
- Test: `backend/tests/test_auth_flow.py`

**Interfaces:**
- Consumes: `get_db`, `User`, `create_access_token`, `create_refresh_token`, `decode_token`, cookie constants, `register_google(oauth)`.
- Produces: routes `GET /api/v1/auth/google/url`, `GET /api/v1/auth/google/callback`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`; `app.api.deps.get_current_user` (FastAPI dependency returning `User`, 401 on missing/invalid cookie); `app.core.oauth.oauth` + `app.core.oauth.register_google`. Callback returns a minimal signed-in HTML page; all four cookies settings: httpOnly, SameSite=Lax, `Secure` when `app_env != "local"`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_flow.py`:

```python
import uuid

import httpx
import pytest

from app.main import create_app


@pytest.mark.asyncio
async def test_google_url_returns_accounts_google(monkeypatch):
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/google/url")
    assert resp.status_code == 200
    assert "accounts.google.com" in resp.json()["url"]


@pytest.mark.asyncio
async def test_me_requires_auth():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_callback_upserts_user_and_sets_cookies(monkeypatch):
    from app.db.sqlalchemy import SessionFactory
    from app.models.user import User

    async def fake_exchange(request):
        return {
            "userinfo": {
                "sub": f"google-sub-{uuid.uuid4()}",
                "email": "student@example.com",
                "name": "Student",
                "picture": "https://example.com/p.png",
            }
        }

    app = create_app()
    monkeypatch.setattr(
        app.state.oauth.google, "authorize_access_token", fake_exchange
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/google/callback?code=abc&state=xyz")
    assert resp.status_code == 200
    assert "ic_access" in resp.cookies and "ic_refresh" in resp.cookies

    async with SessionFactory() as session:
        found = (
            await session.execute(__import__("sqlalchemy").select(User).where(User.email == "student@example.com"))
        ).scalar_one()
        assert found.google_sub.startswith("google-sub-")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_flow.py -v`
Expected: FAIL with collection/import error (`app.main.create_app` has no such routes / `create_app` missing).

- [ ] **Step 3: Implement**

Create `backend/app/core/oauth.py`:

```python
from authlib.integrations.starlette_client import OAuth

from app.core.config import get_settings

oauth = OAuth()


def register_google(oauth: OAuth) -> None:
    settings = get_settings()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
        redirect_uri=settings.google_redirect_uri,
    )
```

Create `backend/app/api/deps.py`:

```python
import uuid

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

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
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user
```

Create `backend/app/api/v1/auth.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
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

router = APIRouter(prefix="/auth", tags=["auth"])

SIGNED_IN_PAGE = """<!doctype html><html><body style="font-family:sans-serif;display:grid;place-items:center;height:100vh">
<div><h2>Signed in to InterviewCopilot</h2><p>You can close this tab.</p></div>
</body></html>"""


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    secure = settings.app_env != "local"
    response.set_cookie(
        IC_ACCESS_COOKIE, access,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True, samesite="lax", secure=secure, path="/",
    )
    response.set_cookie(
        IC_REFRESH_COOKIE, refresh,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True, samesite="lax", secure=secure, path="/",
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
        user.email = userinfo.get("email", user.email)
        user.name = userinfo.get("name", user.name)
        user.picture_url = userinfo.get("picture", user.picture_url)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/google/url")
async def google_auth_url(request: Request):
    resp = await request.app.state.oauth.google.authorize_redirect(
        request, get_settings().google_redirect_uri
    )
    return {"url": resp.headers["location"]}


@router.get("/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    token = await request.app.state.oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=401, detail="Google sign-in failed")
    user = await _upsert_user(db, userinfo)
    response = HTMLResponse(SIGNED_IN_PAGE)
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
        raise HTTPException(status_code=401, detail="Invalid refresh token")
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
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "picture_url": user.picture_url,
    }
```

Create empty `backend/app/api/__init__.py` and `backend/app/api/v1/__init__.py`.

Replace `backend/app/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.auth import router as auth_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.core.oauth import oauth, register_google
from app.db.mongo import get_mongo_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mongo_client = get_mongo_client()
    app.state.mongo_db = app.state.mongo_client[get_settings().mongo_db]
    yield
    app.state.mongo_client.close()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        json_logs=settings.app_env != "local",
    )
    app = FastAPI(title=settings.app_name, docs_url="/docs", lifespan=lifespan)
    register_routes(app)
    register_middleware(app)
    app.state.oauth = oauth
    register_google(oauth)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api/v1")


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=get_settings().jwt_secret)


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_auth_flow.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): google oauth routes, jwt cookies, current-user dependency"
```

---

### Task 5: LLM gateway client + dev llm-check endpoint

**Files:**
- Create: `backend/app/gateway/__init__.py` (empty), `backend/app/gateway/llm.py`
- Create: `backend/app/api/v1/dev.py`
- Modify: `backend/app/main.py` (register dev router)
- Test: `backend/tests/test_gateway.py`

**Interfaces:**
- Consumes: `Settings.litellm_url`, `litellm_master_key`; `app.state.mongo_db` (set in lifespan).
- Produces: `app.gateway.llm.LLMGatewayError` (Exception); `app.gateway.llm.chat_completion(client: httpx.AsyncClient, *, model: str, messages: list[dict], mongo_db: AsyncIOMotorDatabase | None = None, request_id: str | None = None, temperature: float | None = None, response_format: dict | None = None) -> str` — returns assistant content, logs `{request_id, model, latency_ms, prompt_tokens, completion_tokens, total_tokens, prompt_sha256, status, created_at}` to `llm_call_logs` when `mongo_db` given, raises `LLMGatewayError` on HTTP failure. Route `POST /api/v1/dev/llm-check` (`{"prompt": "..."}`) — 404 unless `APP_ENV=local`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_gateway.py`:

```python
import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.gateway.llm import LLMGatewayError, chat_completion


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_chat_completion_returns_content_and_logs():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Bearer " in request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Hello!"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )

    mongo_db = AsyncMongoMockClient()["testdb"]
    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        content = await chat_completion(
            client,
            model="interview-chat",
            messages=[{"role": "user", "content": "hi"}],
            mongo_db=mongo_db,
            request_id="req-1",
        )
    assert content == "Hello!"
    log = await mongo_db.llm_call_logs.find_one({"request_id": "req-1"})
    assert log is not None
    assert log["total_tokens"] == 7
    assert log["model"] == "interview-chat"


@pytest.mark.asyncio
async def test_chat_completion_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        with pytest.raises(LLMGatewayError):
            await chat_completion(
                client,
                model="interview-chat",
                messages=[{"role": "user", "content": "hi"}],
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.gateway'`.

- [ ] **Step 3: Implement**

Create `backend/app/gateway/llm.py`:

```python
import hashlib
import time
from datetime import datetime, timezone

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LLMGatewayError(Exception):
    """Raised when the LLM gateway call fails after retries."""


async def chat_completion(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict],
    mongo_db: AsyncIOMotorDatabase | None = None,
    request_id: str | None = None,
    temperature: float | None = None,
    response_format: dict | None = None,
) -> str:
    """Call the LiteLLM proxy (OpenAI-compatible) and return the assistant content.

    Every successful call is logged to Mongo llm_call_logs (metadata only, never
    full prompts, per spec §7).
    """
    settings = get_settings()
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if response_format is not None:
        payload["response_format"] = response_format

    started = time.monotonic()
    try:
        resp = await client.post(
            f"{settings.litellm_url}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, KeyError) as exc:
        log.error("llm_gateway_failed", model=model, error=str(exc))
        raise LLMGatewayError(f"LLM gateway call failed: {exc}") from exc
    latency_ms = int((time.monotonic() - started) * 1000)

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    if mongo_db is not None:
        await mongo_db.llm_call_logs.insert_one(
            {
                "request_id": request_id,
                "model": model,
                "latency_ms": latency_ms,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "prompt_sha256": hashlib.sha256(repr(messages).encode()).hexdigest(),
                "status": "ok",
                "created_at": datetime.now(timezone.utc),
            }
        )
    return content
```

Create `backend/app/api/v1/dev.py`:

```python
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.gateway.llm import chat_completion

router = APIRouter(prefix="/dev", tags=["dev"])


class LLMCheckRequest(BaseModel):
    prompt: str


@router.post("/llm-check")
async def llm_check(body: LLMCheckRequest, request: Request):
    if get_settings().app_env != "local":
        raise HTTPException(status_code=404, detail="Not found")
    async with httpx.AsyncClient(timeout=70) as client:
        content = await chat_completion(
            client,
            model="interview-chat",
            messages=[{"role": "user", "content": body.prompt}],
            mongo_db=request.app.state.mongo_db,
            request_id=request.headers.get("x-request-id"),
        )
    return {"content": content}
```

Modify `backend/app/main.py` — add import and registration:

```python
from app.api.v1.dev import router as dev_router
```

in `register_routes`:

```python
    app.include_router(dev_router, prefix="/api/v1")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_gateway.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): llm gateway client with mongo call logging + dev llm-check"
```

---

### Task 6: README, full acceptance, push

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything built above.
- Produces: updated quickstart with auth/gateway instructions; M2 acceptance evidence.

- [ ] **Step 1: Update README quickstart section** — append under Quickstart:

```markdown
### Google sign-in (M2)

1. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`
   (Google Cloud Console → OAuth client (Web) → redirect URI
   `http://localhost:8000/api/v1/auth/google/callback`).
2. Start the API and open `http://localhost:8000/api/v1/auth/google/url` in a browser,
   complete consent — you land on "Signed in to InterviewCopilot".
3. `curl -s http://localhost:8000/api/v1/auth/me --cookie "ic_access=<value>"`.

### LLM gateway (M2)

1. Add `GROQ_API_KEY=` (free, console.groq.com) to `.env`, then
   `cd infra && docker compose up -d litellm` (recreate to pick up the key).
2. `curl -s -X POST http://localhost:8000/api/v1/dev/llm-check -H "Content-Type: application/json" -d '{"prompt":"Say hi in 5 words"}'`
   → returns the model's reply; the call is logged in Mongo `llm_call_logs`.
```

- [ ] **Step 2: Full test suite**

Run: `cd backend && uv run pytest -q && uv run ruff check .`
Expected: all tests pass, lint clean.

- [ ] **Step 3: Live acceptance**

1. Start API: `cd backend && uv run uvicorn app.main:app --port 8000`
2. Browser: `http://localhost:8000/api/v1/auth/google/url` → consent → "Signed in" page (requires GOOGLE_CLIENT_ID/SECRET in `.env`).
3. `curl -s -X POST http://localhost:8000/api/v1/dev/llm-check -H "Content-Type: application/json" -d '{"prompt":"Say hi in 5 words"}'` → model reply (requires GROQ_API_KEY + litellm recreated).
4. Check logs: `docker compose exec -T mongo mongosh --quiet interviewcopilot --eval "db.llm_call_logs.find().limit(3).pretty()"` → shows the logged call.

- [ ] **Step 4: Commit and push**

```bash
git add -A
git commit -m "docs: auth + gateway quickstart in README"
git push -u origin feat/m2-auth-gateway
```

---

## M2 Acceptance (from spec §14)

- [ ] Google sign-in works end-to-end in browser (consent → signed-in page → /auth/me with cookie)
- [ ] Gateway chat completion round-trip succeeds (dev/llm-check returns model reply)
- [ ] Call logged in Mongo `llm_call_logs`
- [ ] Full test suite green, lint clean, pushed, PR opened
