from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dev import router as dev_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.tracks import router as tracks_router
from app.api.v1.vault import router as vault_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.core.oauth import oauth, register_google
from app.db.mongo import get_mongo_client
from app.db.sqlalchemy import SessionFactory
from app.services.events import connect_nats


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.gateway.llm import close_http_client, get_http_client

    app.state.mongo_client = get_mongo_client()
    app.state.mongo_db = app.state.mongo_client[get_settings().mongo_db]
    with suppress(Exception):
        # Audit #9: keep conversation lookups indexed from day one.
        await app.state.mongo_db.onboarding_conversations.create_index("user_id", unique=True)
    app.state.nats = await connect_nats()
    # Warm the shared LiteLLM HTTP client (keepalive) once at startup.
    with suppress(Exception):
        await get_http_client()
    yield
    if app.state.nats is not None:
        with suppress(Exception):
            await app.state.nats.drain()
    with suppress(Exception):
        await close_http_client()
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

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        """Local/dev dependency probe: Postgres, NATS, LiteLLM."""
        settings = get_settings()
        checks: dict[str, str] = {}

        try:
            async with SessionFactory() as session:
                await session.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = f"error: {exc.__class__.__name__}"

        nc = getattr(app.state, "nats", None)
        if nc is not None and nc.is_connected:
            checks["nats"] = "ok"
        else:
            checks["nats"] = "disconnected"

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{settings.litellm_url.rstrip('/')}/health/liveliness")
                checks["litellm"] = "ok" if resp.status_code < 500 else f"http_{resp.status_code}"
        except Exception as exc:
            checks["litellm"] = f"error: {exc.__class__.__name__}"

        ready = all(v == "ok" for v in checks.values())
        return JSONResponse(
            {"status": "ready" if ready else "degraded", "checks": checks},
            status_code=200 if ready else 503,
        )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(dev_router, prefix="/api/v1")
    app.include_router(onboarding_router, prefix="/api/v1")
    app.include_router(vault_router, prefix="/api/v1")
    app.include_router(tracks_router, prefix="/api/v1")
    app.include_router(interviews_router, prefix="/api/v1")
    app.include_router(feedback_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    # same_site=lax so the OAuth state cookie is sent on Google's top-level
    # redirect back to /auth/google/callback.
    app.add_middleware(
        SessionMiddleware,
        secret_key=get_settings().session_secret,
        same_site="lax",
        https_only=get_settings().app_env != "local",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app = create_app()
