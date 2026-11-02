import uuid

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import Track
from app.models.user import User


@pytest.mark.asyncio
async def test_session_with_turns(clean_users_table):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"i-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        session.add(track)
        await session.commit()
        await session.refresh(track)

        s = InterviewSession(track_id=track.id, user_id=user.id, mode="strict")
        session.add(s)
        await session.commit()
        await session.refresh(s)

        session.add(
            SessionTurn(
                session_id=s.id,
                turn_index=1,
                question_area="Arrays",
                question="Explain how you would find duplicates.",
            )
        )
        await session.commit()
        assert s.status == "in_progress"
