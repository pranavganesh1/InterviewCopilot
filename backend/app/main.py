from fastapi import FastAPI

from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, docs_url="/docs")
    register_routes(app)
    register_middleware(app)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}


def register_middleware(app: FastAPI) -> None:
    # Middleware is added in Task 2; kept as a seam so order stays explicit.
    pass


app = create_app()
