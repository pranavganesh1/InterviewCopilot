"""Docker API and worker must share one database and one feedback subject."""

from pathlib import Path

from app.services import events
from app.workers import feedback_worker


def test_compose_api_and_worker_share_database_and_nats():
    compose = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.yml"
    text = compose.read_text(encoding="utf-8")
    database = "postgresql+asyncpg://interview:interview@postgres:5432/interviewcopilot"
    nats = "nats://nats:4222"
    assert text.count(f"DATABASE_URL: {database}") >= 2
    assert text.count(f"NATS_URL: {nats}") >= 2
    assert events.FEEDBACK_SUBJECT == "feedback.jobs"
    source = Path(feedback_worker.__file__).read_text(encoding="utf-8")
    assert "feedback_worker_db" in source
    assert "events.FEEDBACK_SUBJECT" in source
