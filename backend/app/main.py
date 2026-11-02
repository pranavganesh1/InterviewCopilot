from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

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
    app.include_router(dev_router, prefix="/api/v1")
    app.include_router(onboarding_router, prefix="/api/v1")
    app.include_router(vault_router, prefix="/api/v1")
    app.include_router(tracks_router, prefix="/api/v1")
    app.include_router(interviews_router, prefix="/api/v1")
    app.include_router(feedback_router, prefix="/api/v1")


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=get_settings().jwt_secret)


app = create_app()
