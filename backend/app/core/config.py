from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[3] is the repo root (shared .env with docker-compose)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_INSECURE_DEFAULTS = {"", "dev-secret-change-me", "dev-session-secret-change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), extra="ignore")

    app_name: str = "InterviewCopilot"
    app_env: str = "local"  # local | staging | prod
    log_level: str = "INFO"

    # Postgres
    database_url: str = "postgresql+asyncpg://interview:interview@localhost:5432/interviewcopilot"

    # MongoDB (host port 27018 — see infra/docker-compose.yml)
    mongo_url: str = "mongodb://localhost:27018"
    mongo_db: str = "interviewcopilot"

    # NATS
    nats_url: str = "nats://localhost:4222"

    # Auth (backend-issued JWT cookie pair)
    jwt_secret: str = "dev-secret-change-me"
    session_secret: str = "dev-session-secret-change-me"
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
    llm_client_timeout: int = 90
    interview_max_turns: int = 12

    # S3-compatible object storage (SeaweedFS)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "local"
    s3_secret_key: str = "local"

    @model_validator(mode="after")
    def _validate_secrets(self):
        """Refuse weak/default secrets outside local development (audit #1)."""
        if self.app_env != "local":
            for name in ("jwt_secret", "session_secret"):
                value = getattr(self, name)
                if value in _INSECURE_DEFAULTS or len(value) < 32:
                    raise ValueError(
                        f"{name} must be a strong unique value (>=32 chars) "
                        f"when app_env={self.app_env!r}"
                    )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
