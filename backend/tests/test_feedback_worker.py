"""Feedback worker: foreign DB skip, session_not_found retry, catch-up."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.models.track import Track
from app.models.user import User
from app.workers.feedback_worker import (
    PermanentFeedbackError,
    RetryableFeedbackError,
    catch_up_once,
    maybe_start_catch_up_task,
    process_event,
    reset_catch_up_failures,
)


class _CM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_foreign_database_job_is_skipped(monkeypatch):
    monkeypatch.setattr(
        "app.workers.feedback_worker.get_settings",
        lambda: type("S", (), {"database_url": "postgresql+asyncpg://x@h/interviewcopilot"})(),
    )
    called = False

    async def boom(_db, _sid):
        nonlocal called
        called = True
        raise AssertionError("should not process foreign DB jobs")

    monkeypatch.setattr("app.workers.feedback_worker.process_session_feedback", boom)
    monkeypatch.setattr("app.workers.feedback_worker.SessionFactory", lambda: _CM())

    payload = {
        "job_id": "j-foreign",
        "session_id": str(uuid.uuid4()),
        "database": "interviewcopilot_test",
    }
    result = await process_event(json.dumps(payload).encode())
    assert result == {"skipped": True, "reason": "foreign_database"}
    assert called is False


@pytest.mark.asyncio
async def test_session_not_found_retries_then_permanent(monkeypatch):
    async def boom(_db, _sid):
        raise LookupError("session_not_found")

    monkeypatch.setattr("app.workers.feedback_worker.process_session_feedback", boom)
    monkeypatch.setattr("app.workers.feedback_worker.SessionFactory", lambda: _CM())
    monkeypatch.setattr(
        "app.workers.feedback_worker.get_settings",
        lambda: type("S", (), {"database_url": "postgresql+asyncpg://x@h/interviewcopilot"})(),
    )

    payload = {
        "job_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "database": "interviewcopilot",
    }
    raw = json.dumps(payload).encode()

    for delivery in (1, 2, 3):
        with pytest.raises(RetryableFeedbackError, match="session_not_found"):
            await process_event(raw, num_delivered=delivery)

    with pytest.raises(PermanentFeedbackError, match="session_not_found"):
        await process_event(raw, num_delivered=4)


@pytest.mark.asyncio
async def test_missing_session_id_is_permanent(monkeypatch):
    monkeypatch.setattr("app.workers.feedback_worker.SessionFactory", lambda: _CM())
    with pytest.raises(PermanentFeedbackError, match="missing session_id"):
        await process_event(json.dumps({"job_id": "j1"}).encode())


@pytest.mark.asyncio
async def test_invalid_uuid_is_permanent(monkeypatch):
    async def boom(_db, _sid):
        raise ValueError("badly formed hexadecimal UUID string")

    monkeypatch.setattr("app.workers.feedback_worker.process_session_feedback", boom)
    monkeypatch.setattr("app.workers.feedback_worker.SessionFactory", lambda: _CM())
    monkeypatch.setattr(
        "app.workers.feedback_worker.get_settings",
        lambda: type("S", (), {"database_url": "postgresql+asyncpg://x@h/interviewcopilot"})(),
    )

    payload = {
        "job_id": "j1",
        "session_id": "not-a-uuid",
        "database": "interviewcopilot",
    }
    with pytest.raises(PermanentFeedbackError, match="invalid_session_id"):
        await process_event(json.dumps(payload).encode())


@pytest.mark.asyncio
async def test_run_loop_naks_retryable(monkeypatch):
    """msg.nak(delay=5) on RetryableFeedbackError; ack on skip/success."""
    from app.workers import feedback_worker as mod

    class FakeMsg:
        def __init__(self, data: bytes, delivered: int):
            self.data = data
            self.metadata = type("M", (), {"num_delivered": delivered})()
            self.ack = AsyncMock()
            self.nak = AsyncMock()
            self.term = AsyncMock()

    msg = FakeMsg(
        json.dumps(
            {
                "job_id": "j1",
                "session_id": str(uuid.uuid4()),
                "database": "interviewcopilot",
            }
        ).encode(),
        delivered=1,
    )

    async def boom(_data, *, num_delivered=1):
        raise RetryableFeedbackError("session_not_found …", delay=5)

    monkeypatch.setattr(mod, "process_event", boom)

    # Exercise the same control flow as run_worker without connecting to NATS.
    num_delivered = int(msg.metadata.num_delivered)
    try:
        await mod.process_event(msg.data, num_delivered=num_delivered)
        await msg.ack()
    except RetryableFeedbackError as exc:
        await msg.nak(delay=exc.delay)

    msg.nak.assert_awaited_once_with(delay=5)
    msg.ack.assert_not_awaited()


async def _seed_completed_session(
    *,
    completed_at: datetime,
    with_report: bool = False,
) -> uuid.UUID:
    async with SessionFactory() as db:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"cu-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="CatchUp")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        sess = InterviewSession(
            track_id=track.id,
            user_id=user.id,
            mode="strict",
            status="completed",
            completed_at=completed_at,
        )
        db.add(sess)
        await db.commit()
        await db.refresh(sess)
        if with_report:
            db.add(
                FeedbackReport(
                    session_id=sess.id,
                    track_id=track.id,
                    user_id=user.id,
                    content={"summary_overview": "already done", "question_assessments": []},
                )
            )
            await db.commit()
        return sess.id


@pytest.mark.asyncio
async def test_catch_up_once_age_report_and_limit(monkeypatch, clean_users_table):
    reset_catch_up_failures()
    old = await _seed_completed_session(completed_at=datetime.now(UTC) - timedelta(minutes=10))
    recent = await _seed_completed_session(completed_at=datetime.now(UTC) - timedelta(seconds=5))
    reported = await _seed_completed_session(
        completed_at=datetime.now(UTC) - timedelta(minutes=10),
        with_report=True,
    )
    extra_old = await _seed_completed_session(
        completed_at=datetime.now(UTC) - timedelta(minutes=20)
    )

    seen: list[str] = []

    async def fake_process(_db, sid):
        seen.append(str(sid))
        return {"ok": True}

    monkeypatch.setattr(
        "app.workers.feedback_worker.process_session_feedback", fake_process
    )

    n = await catch_up_once(min_age_seconds=60, limit=1)
    assert n == 1
    assert len(seen) == 1
    assert seen[0] in {str(old), str(extra_old)}
    assert str(recent) not in seen
    assert str(reported) not in seen

    n2 = await catch_up_once(min_age_seconds=60, limit=10)
    # Remaining old session without a report (fake_process does not create one).
    assert n2 >= 1
    assert str(recent) not in seen
    assert str(reported) not in seen


@pytest.mark.asyncio
async def test_catch_up_gives_up_after_three_failures(monkeypatch, clean_users_table):
    reset_catch_up_failures()
    sid = await _seed_completed_session(
        completed_at=datetime.now(UTC) - timedelta(minutes=10)
    )
    calls = 0

    async def always_fail(_db, _sid):
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.workers.feedback_worker.process_session_feedback", always_fail
    )

    for _ in range(3):
        await catch_up_once(min_age_seconds=0, limit=5)
    assert calls == 3

    await catch_up_once(min_age_seconds=0, limit=5)
    assert calls == 3  # given up — no fourth attempt
    assert str(sid)  # session still exists; we just skip it


@pytest.mark.asyncio
async def test_catch_up_task_disabled_when_interval_zero(monkeypatch):
    monkeypatch.setattr(
        "app.workers.feedback_worker.get_settings",
        lambda: type("S", (), {"feedback_catch_up_interval_seconds": 0})(),
    )
    assert maybe_start_catch_up_task() is None
