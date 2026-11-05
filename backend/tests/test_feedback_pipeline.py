"""End-to-end feedback: complete → publish payload → process → report."""

import json
import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.services.feedback_report_builder import build_report_from_saved_evaluations
from app.services.feedback_service import process_session_feedback
from app.workers.feedback_worker import PermanentFeedbackError, process_event


@pytest.mark.asyncio
async def test_builder_uses_saved_turn_evaluations_only():
    session = InterviewSession(
        id=uuid.uuid4(),
        track_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        mode="strict",
        status="completed",
    )
    answered = [
        SessionTurn(
            session_id=session.id,
            turn_index=1,
            question_area="Hashmaps",
            question="Explain collisions?",
            answer="Use chaining with linked lists.",
            evaluation_coverage="good",
            evaluation_strengths=["Clear mechanism"],
            evaluation_gaps=["No load factor"],
            evaluation_detail={"expected_answer_explanation": "Mention load factor."},
        )
    ]
    # Unanswered turn must not appear in the report.
    report = build_report_from_saved_evaluations(
        session=session,
        answered_turns=answered,
        brief_content={
            "competencies": [{"name": "DSA", "description": "dsa", "importance": "core"}],
            "question_areas": [
                {"topic": "Hashmaps", "guidance": ""},
                {"topic": "Trees", "guidance": ""},
            ],
        },
        max_turns=15,
    )
    assert len(report.question_assessments) == 1
    assert report.question_assessments[0].coverage == "good"
    assert "Trees" in report.unassessed_topics
    assert "Clear mechanism" in report.strengths


@pytest.mark.asyncio
async def test_process_persists_report_when_agent_fails(monkeypatch, clean_users_table):
    async with SessionFactory() as db:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"pipe-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Networking")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        db.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Net",
                    "competencies": [
                        {"name": "TCP", "description": "tcp", "importance": "core"}
                    ],
                    "question_areas": [{"topic": "TCP", "guidance": "handshake"}],
                },
            )
        )
        sess = InterviewSession(
            track_id=track.id, user_id=user.id, mode="strict", status="completed"
        )
        db.add(sess)
        await db.commit()
        await db.refresh(sess)
        db.add(
            SessionTurn(
                session_id=sess.id,
                turn_index=1,
                question_area="TCP",
                question="Explain SYN?",
                answer="Client sends SYN to start handshake.",
                evaluation_coverage="excellent",
                evaluation_strengths=["Accurate"],
                evaluation_gaps=[],
            )
        )
        await db.commit()
        sid = sess.id

    async def boom(**kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(
        "app.services.feedback_service.run_feedback_agent", boom
    )

    async with SessionFactory() as db:
        result = await process_session_feedback(db, sid)
    assert "report" in result
    assert result["report"]["questions_attempted"] == 1
    assert result["report"]["content"]["question_assessments"][0]["coverage"] == "excellent"

    # Unknown session: foreign DB is skipped; same-DB missing session retries then
    # becomes permanent (covered in test_feedback_worker).
    from app.core.config import get_settings

    worker_db = get_settings().database_url.rsplit("/", 1)[-1]
    skipped = await process_event(
        json.dumps(
            {
                "job_id": "j-missing",
                "session_id": str(uuid.uuid4()),
                "database": "other_env",
            }
        ).encode()
    )
    assert skipped.get("skipped") is True

    with pytest.raises(PermanentFeedbackError, match="session_not_found"):
        await process_event(
            json.dumps(
                {
                    "job_id": "j-missing",
                    "session_id": str(uuid.uuid4()),
                    "database": worker_db,
                }
            ).encode(),
            num_delivered=4,
        )


@pytest.mark.asyncio
async def test_complete_publishes_existing_session_id(monkeypatch, clean_users_table):
    from app.agents.interviewer import TurnDecision

    published: list[dict] = []

    async def fake_publish(session_id, track_id, user_id, nc=None):
        published.append(
            {
                "session_id": str(session_id),
                "track_id": str(track_id),
                "user_id": str(user_id),
            }
        )

    async def fake_turn(*args, **kwargs):
        payload = kwargs.get("payload") or (args[0] if args else {})
        if not payload.get("transcript"):
            return TurnDecision(
                evaluation={"coverage": "none", "strengths": [], "gaps": []},
                decision="next_area",
                next_question="Q1?",
                question_area="TCP",
            )
        return TurnDecision(
            evaluation={
                "coverage": "good",
                "strengths": ["ok"],
                "gaps": [],
                "expected_answer_explanation": "detail",
            },
            decision="follow_up",
            next_question="Q2?",
            question_area="TCP",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    monkeypatch.setattr("app.services.interview_service.publish_feedback_job", fake_publish)

    async with SessionFactory() as db:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"pub-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Net")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        db.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Net",
                    "competencies": [{"name": "TCP", "description": "t", "importance": "core"}],
                    "question_areas": [{"topic": "TCP", "guidance": "g"}],
                },
            )
        )
        await db.commit()
        token = create_access_token(str(user.id))
        track_id = track.id

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            cookies={"ic_access": token},
            json={"mode": "strict"},
        )
        assert r.status_code == 201
        sid = r.json()["session"]["id"]

        # Session must exist in Postgres before complete.
        async with SessionFactory() as db:
            assert await db.get(InterviewSession, uuid.UUID(sid)) is not None

        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            cookies={"ic_access": token},
            json={"answer": "SYN starts the handshake."},
        )
        assert r.status_code == 200
        assert r.json()["completed"] is False

        r = await client.post(
            f"/api/v1/sessions/{sid}/complete",
            cookies={"ic_access": token},
        )
        assert r.status_code == 200
        assert r.json()["session"]["status"] == "completed"

    assert len(published) == 1
    assert published[0]["session_id"] == sid

    # Worker-style processing finds the same session and writes a report.
    async def boom(**kwargs):
        raise RuntimeError("skip llm")

    monkeypatch.setattr("app.services.feedback_service.run_feedback_agent", boom)
    async with SessionFactory() as db:
        out = await process_session_feedback(db, sid)
    assert out["report"]["session_id"] == sid
    from sqlalchemy import select

    async with SessionFactory() as db:
        report = (
            await db.execute(
                select(FeedbackReport).where(FeedbackReport.session_id == uuid.UUID(sid))
            )
        ).scalar_one()
        assert report.user_id is not None
        assert report.content["question_assessments"]
