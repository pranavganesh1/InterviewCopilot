from app.core.config import PROJECT_ROOT, get_settings


def test_settings_load_from_root_env():
    settings = get_settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.mongo_db == "interviewcopilot"
    assert settings.litellm_url == "http://localhost:4000"
    assert PROJECT_ROOT.name == "InterviewCopilot"
