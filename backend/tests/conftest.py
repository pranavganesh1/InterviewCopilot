import os

# Tests run against a dedicated database so fixture cleanup never touches
# real data. Must be set before any app module imports config (lru_cache).
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://interview:interview@localhost:5432/interviewcopilot_test"
)

import pytest  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.agents import question_plan  # noqa: E402
from app.db.sqlalchemy import SessionFactory  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_question_plan_llm(monkeypatch):
    """M11: build_question_plan's LLM call made start_session take 137s under
    quota pressure (gateway backoff). Tests get the deterministic plan — the
    LLM path is covered by dedicated mocked tests in test_question_plan.py.
    """

    async def _stub(brief_content, n):
        return question_plan.deterministic_question_plan(
            brief_content, n, seed=(brief_content or {}).get("plan_seed")
        )

    monkeypatch.setattr(
        question_plan,
        "build_question_plan",
        _stub,
    )


from app.models.feedback import FeedbackReport, ProgressionState  # noqa: E402
from app.models.interview import InterviewSession, SessionTurn  # noqa: E402
from app.models.track import InterviewBrief, Track  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vault import VaultItem  # noqa: E402


@pytest.fixture(autouse=True)
def _noop_publish_feedback_job(monkeypatch):
    """Prevent ASGITransport tests from publishing real JetStream jobs.

    Tests that need a spy can still monkeypatch either import path; this
    fixture only stops the default path from hitting the shared NATS.
    """

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.services.interview_service.publish_feedback_job", _noop)
    monkeypatch.setattr("app.services.events.publish_feedback_job", _noop)


@pytest.fixture
async def clean_users_table():
    """Remove vault items and users after a DB-touching test (test DB only)."""
    yield
    async with SessionFactory() as session:
        await session.execute(delete(FeedbackReport))
        await session.execute(delete(ProgressionState))
        await session.execute(delete(SessionTurn))
        await session.execute(delete(InterviewSession))
        await session.execute(delete(InterviewBrief))
        await session.execute(delete(Track))
        await session.execute(delete(VaultItem))
        await session.execute(delete(User))
        await session.commit()
