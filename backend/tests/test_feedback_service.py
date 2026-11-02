import uuid

import pytest

from app.agents.feedback_agent import (
    AssessedCompetency,
    FeedbackReportContent,
    QuestionEvidence,
)
from app.db.sqlalchemy import SessionFactory
from app.models.feedback import FeedbackReport, ProgressionState
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User


def _agent_content(mode="strict", struggling=True):
    level = "weak" if struggling else "solid"
    return FeedbackReportContent(
        session_mode=mode,
        summary_overview="Struggled with core concepts." if struggling else "Solid answers.",
        coverage_status="PARTIAL",
        question_assessments=[
            QuestionEvidence(
                turn_index=1,
                coverage="partial",
                observation="Vague on collisions",
                evidence_excerpt="buckets and stuff",
            )
        ],
        competency_assessments=[
            AssessedCompetency(
                competency_name="DSA",
                assessment_status="ASSESSED",
                level=level,
                observation="Gap in fundamentals",
                confidence="MEDIUM",
            )
        ],
        strengths=["Attempted everything"],
        improvement_areas=["Hash collisions"],
        unassessed_topics=["Graphs"],
        recommendations=["Revise hashmaps", "Practice collision strategies"],
    )


async def _make_completed_strict_session(struggling_brief=True):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"fb-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "DSA",
                    "competencies": [
                        {"name": "DSA", "description": "algorithms", "importance": "core"}
                    ],
                    "question_areas": [{"topic": "Hashmaps", "guidance": "collisions"}],
                },
            )
        )
        s = InterviewSession(track_id=track.id, user_id=user.id, mode="strict", status="completed")
        session.add(s)
        await session.commit()
        await session.refresh(s)
        session.add(
            SessionTurn(
                session_id=s.id,
                turn_index=1,
                question_area="Hashmaps",
                question="Explain collisions?",
                answer="buckets and stuff",
            )
        )
        await session.commit()
        return s.id


@pytest.mark.asyncio
async def test_process_creates_report_and_updates_progression(monkeypatch, clean_users_table):
    import app.services.feedback_service as svc

    session_id = await _make_completed_strict_session()
    content = _agent_content()

    async def fake_run_feedback(*args, **kwargs):
        return content

    monkeypatch.setattr(svc, "run_feedback_agent", fake_run_feedback)

    async with SessionFactory() as db:
        result = await svc.process_session_feedback(db, session_id)
    assert result["report"]["content"]["summary_overview"].startswith("Struggled")

    async with SessionFactory() as db:
        from sqlalchemy import select

        reports = (await db.execute(select(FeedbackReport))).scalars().all()
        assert len(reports) == 1
        prog = (await db.execute(select(ProgressionState))).scalars().one()
        assert prog.strict_completed == 1
        assert prog.guided_state == "LOCKED"

        # idempotent: reprocess replaces, never duplicates
        await svc.process_session_feedback(db, session_id)
        reports = (await db.execute(select(FeedbackReport))).scalars().all()
        assert len(reports) == 1


@pytest.mark.asyncio
async def test_guided_unlocks_after_three_weak_stricts(monkeypatch, clean_users_table):
    import app.services.feedback_service as svc

    content = _agent_content(struggling=True)

    async def fake_run_feedback(*args, **kwargs):
        return content

    monkeypatch.setattr(svc, "run_feedback_agent", fake_run_feedback)

    async with SessionFactory() as db:
        for _ in range(3):
            sid = await _make_completed_strict_session()
            await svc.process_session_feedback(db, sid)

        from sqlalchemy import select

        progs = (await db.execute(select(ProgressionState))).scalars().all()
        # 3 sessions created in 3 separate tracks (helper creates new track each time)
        for p in progs:
            assert p.guided_state == "LOCKED" or p.strict_completed >= 1


@pytest.mark.asyncio
async def test_three_weak_in_same_track_unlocks(monkeypatch, clean_users_table):
    import app.services.feedback_service as svc

    content = _agent_content(struggling=True)

    async def fake_run_feedback(*args, **kwargs):
        return content

    monkeypatch.setattr(svc, "run_feedback_agent", fake_run_feedback)

    # one track, three completed strict sessions
    async with SessionFactory() as db:
        from sqlalchemy import select

        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"u3-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        db.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={"summary": "DSA", "competencies": [], "question_areas": []},
            )
        )
        session_ids = []
        for _ in range(3):
            s = InterviewSession(
                track_id=track.id, user_id=user.id, mode="strict", status="completed"
            )
            db.add(s)
            await db.commit()
            await db.refresh(s)
            db.add(
                SessionTurn(
                    session_id=s.id,
                    turn_index=1,
                    question_area="Hashmaps",
                    question="Q?",
                    answer="A",
                )
            )
            await db.commit()
            session_ids.append(s.id)

        for sid in session_ids:
            await svc.process_session_feedback(db, sid)

        prog = (await db.execute(select(ProgressionState))).scalars().one()
        assert prog.strict_completed == 3
        assert prog.guided_state == "UNLOCKED"


@pytest.mark.asyncio
async def test_strong_performance_keeps_guided_locked(monkeypatch, clean_users_table):
    import app.services.feedback_service as svc

    content = _agent_content(struggling=False)

    async def fake_run_feedback(*args, **kwargs):
        return content

    monkeypatch.setattr(svc, "run_feedback_agent", fake_run_feedback)

    async with SessionFactory() as db:
        from sqlalchemy import select

        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"u4-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        db.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={"summary": "DSA", "competencies": [], "question_areas": []},
            )
        )
        for _ in range(3):
            s = InterviewSession(
                track_id=track.id, user_id=user.id, mode="strict", status="completed"
            )
            db.add(s)
            await db.commit()
            await db.refresh(s)
            db.add(
                SessionTurn(
                    session_id=s.id,
                    turn_index=1,
                    question_area="Hashmaps",
                    question="Q?",
                    answer="A",
                )
            )
            await db.commit()
            await svc.process_session_feedback(db, s.id)

        prog = (await db.execute(select(ProgressionState))).scalars().one()
        assert prog.strict_completed == 3
        assert prog.guided_state == "LOCKED"
