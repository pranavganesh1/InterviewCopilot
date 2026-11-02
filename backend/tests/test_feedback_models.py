import uuid

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.feedback import FeedbackReport, ProgressionState
from app.models.interview import InterviewSession
from app.models.track import Track
from app.models.user import User


@pytest.mark.asyncio
async def test_report_and_progression_roundtrip(clean_users_table):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"f-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        s = InterviewSession(track_id=track.id, user_id=user.id, mode="strict", status="completed")
        session.add(s)
        await session.commit()
        await session.refresh(s)

        report = FeedbackReport(
            session_id=s.id,
            track_id=track.id,
            user_id=user.id,
            content={"summary_overview": "solid on arrays"},
        )
        session.add(report)
        prog = ProgressionState(track_id=track.id)
        session.add(prog)
        await session.commit()
        await session.refresh(report)
        await session.refresh(prog)

        assert report.id is not None
        assert prog.strict_completed == 0
        assert prog.guided_state == "LOCKED"
