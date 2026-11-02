import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, get_settings


def test_settings_load_from_root_env():
    settings = get_settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.mongo_db == "interviewcopilot"
    assert settings.litellm_url == "http://localhost:4000"
    assert PROJECT_ROOT.name == "InterviewCopilot"


def test_prod_rejects_default_jwt_secret():
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            app_env="prod",
            jwt_secret="dev-secret-change-me",
            session_secret="dev-session-secret-change-me",
        )


def test_prod_rejects_short_jwt_secret():
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(app_env="prod", jwt_secret="short", session_secret="x" * 40)


def test_prod_accepts_strong_secrets():
    from app.core.config import Settings

    s = Settings(app_env="prod", jwt_secret="a" * 40, session_secret="b" * 40)
    assert s.app_env == "prod"


def test_local_allows_dev_defaults():
    from app.core.config import Settings

    s = Settings(app_env="local")
    assert s.jwt_secret == "dev-secret-change-me"
