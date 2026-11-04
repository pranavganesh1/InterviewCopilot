"""Feedback worker: permanent failures must not loop via nak forever."""

import json
import uuid

import pytest

from app.workers.feedback_worker import PermanentFeedbackError, process_event


class _CM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_missing_session_is_permanent_failure(monkeypatch):
    async def boom(_db, _sid):
        raise LookupError("session_not_found")

    monkeypatch.setattr("app.workers.feedback_worker.process_session_feedback", boom)
    monkeypatch.setattr("app.workers.feedback_worker.SessionFactory", lambda: _CM())

    payload = {"job_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4())}
    with pytest.raises(PermanentFeedbackError, match="session_not_found"):
        await process_event(json.dumps(payload).encode())


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

    payload = {"job_id": "j1", "session_id": "not-a-uuid"}
    with pytest.raises(PermanentFeedbackError, match="invalid_session_id"):
        await process_event(json.dumps(payload).encode())
