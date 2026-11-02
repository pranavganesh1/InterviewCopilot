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
    database_url: str = "postgresql+asyncpg://interview:interview@localhost:5432/interviewcopilot"

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
