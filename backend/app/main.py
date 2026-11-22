import asyncio
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
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware
from app.core.oauth import oauth, register_google
from app.db.mongo import get_mongo_client
from app.db.s3 import RESUME_BUCKET, get_s3_client
from app.db.sqlalchemy import SessionFactory
from app.services.events import connect_nats

log = get_logger(__name__)

# Keep readiness probes short so orchestrators are not blocked on a hung dependency.
_READYZ_TIMEOUT_S = 3.0


def _check_error(exc: BaseException) -> str:
    """Safe check failure label — class name only, never message/URLs/secrets."""
    return f"error: {exc.__class__.__name__}"


async def _probe_postgres() -> str:
    try:
        async with asyncio.timeout(_READYZ_TIMEOUT_S):
            async with SessionFactory() as session:
                await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        log.warning("readyz_check_failed", check="postgres", error_class=exc.__class__.__name__)
        return _check_error(exc)


async def _probe_mongo(app: FastAPI) -> str:
    mongo_db = getattr(app.state, "mongo_db", None)
    if mongo_db is None:
        log.warning("readyz_check_failed", check="mongo", error_class="Unavailable")
        return "error: Unavailable"
    try:
        async with asyncio.timeout(_READYZ_TIMEOUT_S):
            await mongo_db.command("ping")
        return "ok"
    except Exception as exc:
        log.warning("readyz_check_failed", check="mongo", error_class=exc.__class__.__name__)
        return _check_error(exc)


async def _probe_nats(app: FastAPI) -> str:
    nc = getattr(app.state, "nats", None)
    if nc is not None and getattr(nc, "is_connected", False):
        return "ok"
    return "disconnected"


async def _probe_litellm(litellm_url: str) -> str:
    try:
        async with asyncio.timeout(_READYZ_TIMEOUT_S):
            async with httpx.AsyncClient(timeout=_READYZ_TIMEOUT_S) as client:
                resp = await client.get(f"{litellm_url.rstrip('/')}/health/liveliness")
        if resp.status_code < 500:
            return "ok"
        return f"http_{resp.status_code}"
    except Exception as exc:
        log.warning("readyz_check_failed", check="litellm", error_class=exc.__class__.__name__)
        return _check_error(exc)


async def _probe_s3(app: FastAPI) -> str:
    """Lightweight bucket probe only — never create/mutate objects or buckets."""
    s3 = getattr(app.state, "s3", None)
    if s3 is None:
        log.warning("readyz_check_failed", check="s3", error_class="Unavailable")
        return "error: Unavailable"
    try:
        async with asyncio.timeout(_READYZ_TIMEOUT_S):
            await asyncio.to_thread(s3.head_bucket, Bucket=RESUME_BUCKET)
        return "ok"
    except Exception as exc:
        log.warning("readyz_check_failed", check="s3", error_class=exc.__class__.__name__)
        return _check_error(exc)


async def collect_readyz_checks(app: FastAPI, *, litellm_url: str) -> dict[str, str]:
    """Run required dependency probes concurrently; values are 'ok' or safe labels."""
    postgres, mongo, nats, litellm, s3 = await asyncio.gather(
        _probe_postgres(),
        _probe_mongo(app),
        _probe_nats(app),
        _probe_litellm(litellm_url),
        _probe_s3(app),
    )
    return {
        "postgres": postgres,
        "mongo": mongo,
        "nats": nats,
        "litellm": litellm,
        "s3": s3,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.gateway.llm import close_http_client, get_http_client

    app.state.mongo_client = get_mongo_client()
    app.state.mongo_db = app.state.mongo_client[get_settings().mongo_db]
    # Reuse one S3 client for readiness + request paths that opt into app.state.
    with suppress(Exception):
        app.state.s3 = get_s3_client()
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
        """Dependency probe: Postgres, Mongo, NATS, LiteLLM, S3 (required)."""
        settings = get_settings()
        checks = await collect_readyz_checks(app, litellm_url=settings.litellm_url)
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
