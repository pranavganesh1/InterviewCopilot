"""Soft-delete tracks: hide them from lists without removing history."""

import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import Track
from app.models.user import User


async def _user(prefix: str = "owner") -> tuple[User, str]:
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"{prefix}-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, create_access_token(str(user.id))


async def _track(user: User, subject: str = "Graphs") -> Track:
    async with SessionFactory() as session:
        track = Track(user_id=user.id, track_type="topic", subject=subject)
        session.add(track)
        await session.commit()
        await session.refresh(track)
        return track


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_delete_archives_and_keeps_history(clean_users_table):
    from app.main import create_app

    user, token = await _user()
    track = await _track(user)
    async with SessionFactory() as session:
        interview = InterviewSession(
            track_id=track.id, user_id=user.id, mode="strict", status="completed"
        )
        session.add(interview)
        await session.commit()
        await session.refresh(interview)
        turn = SessionTurn(
            session_id=interview.id,
            turn_index=1,
            question_area="Graphs",
            question="What is BFS?",
            answer="Level-order search.",
        )
        report = FeedbackReport(
            session_id=interview.id,
            track_id=track.id,
            user_id=user.id,
            content={
                "summary_overview": "Kept.",
                "coverage_status": "PARTIAL",
                "question_assessments": [{"turn_index": 1, "coverage": "good"}],
            },
        )
        session.add_all([turn, report])
        await session.commit()
        await session.refresh(turn)
        await session.refresh(report)
        ids = (interview.id, turn.id, report.id)

    app = create_app()
    async with _client(app) as client:
        cookies = {"ic_access": token}
        first = await client.delete(f"/api/v1/tracks/{track.id}", cookies=cookies)
        assert first.status_code == 200
        archived_at = first.json()["track"]["archived_at"]
        assert first.json()["track"]["archived"] is True
        second = await client.delete(f"/api/v1/tracks/{track.id}", cookies=cookies)
        assert second.status_code == 200
        assert second.json()["track"]["archived_at"] == archived_at

        listed = await client.get("/api/v1/tracks", cookies=cookies)
        assert listed.status_code == 200
        assert listed.json() == []
        included = await client.get("/api/v1/tracks?include_archived=true", cookies=cookies)
        assert included.json()[0]["id"] == str(track.id)
        assert included.json()[0]["archived"] is True

        stats = await client.get("/api/v1/me/assessments", cookies=cookies)
        body = stats.json()
        assert body["dashboard"]["completed_interviews"] == 0
        assert body["assessments"][0]["track_archived"] is True

        report_resp = await client.get(f"/api/v1/sessions/{ids[0]}/report", cookies=cookies)
        assert report_resp.status_code == 200

        start = await client.post(
            f"/api/v1/tracks/{track.id}/sessions",
            json={"mode": "strict", "duration_minutes": 30},
            cookies=cookies,
        )
        assert start.status_code == 409
        assert "archived" in start.json()["detail"].lower()

        restored = await client.post(f"/api/v1/tracks/{track.id}/restore", cookies=cookies)
        assert restored.status_code == 200
        assert restored.json()["track"]["archived"] is False
        again = await client.post(f"/api/v1/tracks/{track.id}/restore", cookies=cookies)
        assert again.status_code == 200
        assert again.json()["track"]["archived_at"] is None
        back = await client.get("/api/v1/tracks", cookies=cookies)
        assert back.json()[0]["id"] == str(track.id)
        stats = await client.get("/api/v1/me/assessments", cookies=cookies)
        assert stats.json()["dashboard"]["completed_interviews"] == 1

    async with SessionFactory() as session:
        assert await session.get(Track, track.id) is not None
        assert await session.get(InterviewSession, ids[0]) is not None
        assert await session.get(SessionTurn, ids[1]) is not None
        assert await session.get(FeedbackReport, ids[2]) is not None


@pytest.mark.asyncio
async def test_delete_is_owner_only_and_blocks_open_session(clean_users_table):
    from app.main import create_app

    owner, owner_token = await _user("owner")
    _other, other_token = await _user("other")
    track = await _track(owner, "Trees")
    async with SessionFactory() as session:
        interview = InterviewSession(
            track_id=track.id, user_id=owner.id, mode="strict", status="in_progress"
        )
        session.add(interview)
        await session.commit()
        await session.refresh(interview)
        session_id = interview.id

    app = create_app()
    async with _client(app) as client:
        missing = await client.delete(
            f"/api/v1/tracks/{track.id}", cookies={"ic_access": other_token}
        )
        assert missing.status_code == 404
        unknown = await client.delete(
            f"/api/v1/tracks/{uuid.uuid4()}", cookies={"ic_access": owner_token}
        )
        assert unknown.status_code == 404
        # M11: deleting a track with an unfinished interview now SUCCEEDS —
        # the open session is auto-closed as aborted (user owns the call).
        blocked = await client.delete(
            f"/api/v1/tracks/{track.id}", cookies={"ic_access": owner_token}
        )
        assert blocked.status_code == 200

    async with SessionFactory() as session:
        saved = await session.get(Track, track.id)
        assert saved is not None
        assert saved.archived_at is not None
        still_open = await session.get(InterviewSession, session_id)
        assert still_open is not None
        assert still_open.status == "aborted"


@pytest.mark.asyncio
async def test_worker_completes_feedback_for_archived_track(monkeypatch, clean_users_table):
    from app.services import feedback_service
    from app.workers.feedback_worker import process_event

    async def _fail(**_kwargs):
        raise RuntimeError("stubbed")

    monkeypatch.setattr(feedback_service, "run_feedback_agent", _fail)

    user, _token = await _user("worker")
    track = await _track(user, "Queues")
    async with SessionFactory() as session:
        interview = InterviewSession(
            track_id=track.id, user_id=user.id, mode="strict", status="completed"
        )
        session.add(interview)
        await session.commit()
        await session.refresh(interview)
        session.add(
            SessionTurn(
                session_id=interview.id,
                turn_index=1,
                question_area="Queues",
                question="When would you use a queue?",
                answer="Breadth-first work.",
                evaluation_coverage="good",
            )
        )
        saved = await session.get(Track, track.id)
        saved.archived_at = saved.created_at
        await session.commit()
        session_id = interview.id

    result = await process_event(json.dumps({"session_id": str(session_id)}).encode())
    assert result.get("skipped") is None

    async with SessionFactory() as session:
        report = (
            await session.execute(
                select(FeedbackReport).where(FeedbackReport.session_id == session_id)
            )
        ).scalar_one_or_none()
        assert report is not None
        still = await session.get(Track, track.id)
        assert still is not None
        assert still.archived_at is not None


@pytest.mark.asyncio
async def test_admin_user_detail_includes_archived_tracks(clean_users_table):
    from app.services import admin_service

    user, _token = await _user("member")
    visible = await _track(user, "Visible")
    hidden = await _track(user, "Hidden")
    async with SessionFactory() as session:
        row = await session.get(Track, hidden.id)
        row.archived_at = row.created_at
        await session.commit()

    class _Agg:
        async def to_list(self, _length):
            return []

    class _Logs:
        def aggregate(self, _pipeline):
            return _Agg()

    class _Mongo:
        llm_call_logs = _Logs()

    async with SessionFactory() as session:
        detail = await admin_service.user_detail(session, _Mongo(), user.id)
    subjects = {item["subject"]: item["archived"] for item in detail["tracks"]}
    assert subjects[visible.subject] is False
    assert subjects[hidden.subject] is True
