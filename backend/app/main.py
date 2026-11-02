from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        json_logs=settings.app_env != "local",  # pretty console logs locally
    )
    app = FastAPI(title=settings.app_name, docs_url="/docs")
    register_routes(app)
    register_middleware(app)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)


app = create_app()
