"""Deadline, single feedback job, quota retry, and answered-only reports."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.gateway.llm import LLMGatewayError, llm_model_used
from app.main import create_app
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.services.interview_service import _as_utc, _minutes_remaining, _session_timed_out


async def _seed(monkeypatch):
    from app.agents.interviewer import TurnDecision

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"tm-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Timers")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Timers",
                    "competencies": [{"name": "Time", "description": "t", "importance": "core"}],
                    "question_areas": [{"topic": "Clocks", "guidance": "deadlines"}],
                },
            )
        )
        await session.commit()

    calls = {"n": 0}

    async def fake_turn(*args, **kwargs):
        calls["n"] += 1
        llm_model_used.set("structured-json")
        if calls["n"] == 1:
            return TurnDecision(
                evaluation={"coverage": "none", "strengths": [], "gaps": []},
                decision="next_area",
                next_question="What is a deadline?",
                question_area="Clocks",
            )
        if calls.get("raise_once"):
            calls["raise_once"] = False
            raise LLMGatewayError("provider quota exhausted")
        return TurnDecision(
            evaluation={"coverage": "good", "strengths": ["clear"], "gaps": []},
            decision="follow_up",
            next_question="How do you detect that time is up?",
            question_area="Clocks",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    return user, create_access_token(str(user.id)), track.id, calls


def _capture(monkeypatch):
    published: list[str] = []

    async def fake_publish(session_id, track_id, user_id, nc=None):
        published.append(str(session_id))

    monkeypatch.setattr("app.services.interview_service.publish_feedback_job", fake_publish)
    return published


async def _start(token, track_id):
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "duration_minutes": 15},
            cookies={"ic_access": token},
        )
    assert started.status_code == 201
    return started.json()["session"]["id"]


@pytest.mark.asyncio
async def test_deadline_rejects_answer_and_finishes_once(monkeypatch, clean_users_table):
    user, token, track_id, _calls = await _seed(monkeypatch)
    published = _capture(monkeypatch)
    session_id = await _start(token, track_id)

    monkeypatch.setattr(
        "app.services.interview_service._minutes_remaining",
        lambda _session: 0,
    )
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        late = await client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"answer": "this answer is too late to count"},
            cookies={"ic_access": token},
        )
        again = await client.post(
            f"/api/v1/sessions/{session_id}/complete",
            cookies={"ic_access": token},
        )
    assert late.status_code == 409
    assert "deadline" in late.json()["detail"].lower()
    assert again.status_code == 200
    assert published == [session_id]

    async with SessionFactory() as db:
        session = await db.get(InterviewSession, uuid.UUID(session_id))
        turns = (
            await db.execute(
                SessionTurn.__table__.select().where(SessionTurn.session_id == session.id)
            )
        ).all()
    assert session.status == "completed"
    assert all(row.answer is None for row in turns)


@pytest.mark.asyncio
async def test_expiry_and_manual_finish_publish_one_job(monkeypatch, clean_users_table):
    _user, token, track_id, _calls = await _seed(monkeypatch)
    published = _capture(monkeypatch)
    session_id = await _start(token, track_id)
    sid = uuid.UUID(session_id)

    from app.services.interview_service import _finish

    async def finish_once():
        async with SessionFactory() as db:
            session = await db.get(InterviewSession, sid)
            user = await db.get(User, session.user_id)
            # _finish does not check ownership; complete_session does.
            assert user is not None
            return await _finish(db, session)

    first, second = await asyncio.gather(finish_once(), finish_once())
    assert sorted([first, second]) == [False, True]
    assert published == [session_id]

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        manual = await client.post(
            f"/api/v1/sessions/{session_id}/complete",
            cookies={"ic_access": token},
        )
    assert manual.status_code == 200
    assert published == [session_id]


@pytest.mark.asyncio
async def test_quota_retry_does_not_duplicate_the_turn(monkeypatch, clean_users_table):
    _user, token, track_id, calls = await _seed(monkeypatch)
    session_id = await _start(token, track_id)
    calls["raise_once"] = True

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    answer = "A deadline is the moment the session must stop."
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        failed = await client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"answer": answer},
            cookies={"ic_access": token},
        )
        retried = await client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"answer": answer},
            cookies={"ic_access": token},
        )
        fetched = await client.get(
            f"/api/v1/sessions/{session_id}",
            cookies={"ic_access": token},
        )
    assert failed.status_code == 503
    assert "retry" in failed.json()["detail"].lower()
    assert retried.status_code == 200
    turns = fetched.json()["turns"]
    answered = [t for t in turns if t.get("answer") == answer]
    assert len(answered) == 1
    assert answered[0]["evaluation"]["coverage"] == "good"
    assert answered[0]["evaluation"]  # saved on the original turn
    assert fetched.json()["turns"][0]["turn_index"] == 1

    async with SessionFactory() as db:
        turn = (
            await db.execute(
                SessionTurn.__table__.select().where(
                    SessionTurn.session_id == uuid.UUID(session_id),
                    SessionTurn.turn_index == 1,
                )
            )
        ).one()
    assert turn.evaluation_detail["model"] == "structured-json"


@pytest.mark.asyncio
async def test_report_drops_unanswered_questions(monkeypatch, clean_users_table):
    from app.agents.feedback_agent import FeedbackReportContent
    from app.services.feedback_service import process_session_feedback

    async with SessionFactory() as db:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"rp-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Reports")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        db.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "R",
                    "competencies": [{"name": "C", "description": "c", "importance": "core"}],
                    "question_areas": [{"topic": "Clocks", "guidance": ""}],
                },
            )
        )
        session = InterviewSession(
            track_id=track.id, user_id=user.id, mode="strict", status="completed"
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        db.add(
            SessionTurn(
                session_id=session.id,
                turn_index=1,
                question_area="Clocks",
                question="Answered?",
                answer="Yes, with a concrete example of a timer.",
                evaluation_coverage="good",
                evaluation_strengths=["concrete"],
                evaluation_gaps=[],
            )
        )
        db.add(
            SessionTurn(
                session_id=session.id,
                turn_index=2,
                question_area="Clocks",
                question="Still open?",
                answer=None,
            )
        )
        await db.commit()
        sid = session.id

    async def extra_report(**kwargs):
        return FeedbackReportContent(
            session_mode="strict",
            summary_overview="agent added an extra question",
            coverage_status="PARTIAL",
            question_assessments=[
                {
                    "turn_index": 1,
                    "coverage": "good",
                    "observation": "ok",
                    "evidence_excerpt": "timer",
                },
                {
                    "turn_index": 2,
                    "coverage": "none",
                    "observation": "should be dropped",
                    "evidence_excerpt": "",
                },
            ],
        )

    monkeypatch.setattr("app.services.feedback_service.run_feedback_agent", extra_report)
    async with SessionFactory() as db:
        result = await process_session_feedback(db, sid)
    assessments = result["report"]["content"]["question_assessments"]
    assert [row["turn_index"] for row in assessments] == [1]
    assert result["report"]["questions_attempted"] == 1


def test_minutes_remaining_handles_naive_and_aware_created_at():
    aware = type(
        "S",
        (),
        {
            "duration_minutes": 30,
            "created_at": datetime.now(UTC) - timedelta(minutes=5),
        },
    )()
    naive = type(
        "S",
        (),
        {
            "duration_minutes": 30,
            "created_at": datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5),
        },
    )()
    assert 24 <= _minutes_remaining(aware) <= 26
    assert 24 <= _minutes_remaining(naive) <= 26
    assert not _session_timed_out(aware)
    fresh = type(
        "S",
        (),
        {"duration_minutes": 60, "created_at": datetime.now(UTC)},
    )()
    assert _minutes_remaining(fresh) > 55
    assert not _session_timed_out(fresh)
    expired = type(
        "S",
        (),
        {
            "duration_minutes": 15,
            "created_at": datetime.now(UTC) - timedelta(minutes=20),
        },
    )()
    assert _session_timed_out(expired)
    assert _as_utc(naive.created_at).tzinfo is not None


@pytest.mark.asyncio
async def test_start_does_not_reuse_expired_empty_session(monkeypatch, clean_users_table):
    """Abandoned Q1 past the deadline must not be returned as a 'new' assessment."""
    user, token, track_id, _calls = await _seed(monkeypatch)
    _capture(monkeypatch)
    old_id = await _start(token, track_id)

    async with SessionFactory() as db:
        session = await db.get(InterviewSession, uuid.UUID(old_id))
        assert session is not None
        session.created_at = datetime.now(UTC) - timedelta(hours=3)
        session.duration_minutes = 30
        await db.commit()
        assert _session_timed_out(session)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        again = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict", "duration_minutes": 30},
            cookies={"ic_access": token},
        )
        assert again.status_code == 201
        body = again.json()
        new_id = body["session"]["id"]
        assert new_id != old_id
        created = datetime.fromisoformat(body["session"]["created_at"])
        assert created.tzinfo is not None
        # Fresh timer — not immediately expired.
        assert (datetime.now(UTC) - created.astimezone(UTC)).total_seconds() < 120

        answered = await client.post(
            f"/api/v1/sessions/{new_id}/turns",
            json={"answer": "A deadline is when the timer hits zero."},
            cookies={"ic_access": token},
        )
        assert answered.status_code == 200
        assert "deadline" not in str(answered.json()).lower()

    async with SessionFactory() as db:
        old = await db.get(InterviewSession, uuid.UUID(old_id))
        new = await db.get(InterviewSession, uuid.UUID(new_id))
        assert old is not None and old.status == "aborted"
        assert new is not None and new.status == "in_progress"
        assert not _session_timed_out(new)
