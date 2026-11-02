import uuid

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.track import InterviewBrief, Track
from app.models.user import User


@pytest.mark.asyncio
async def test_track_with_versioned_briefs(clean_users_table):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"t-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        track = Track(user_id=user.id, track_type="topic", subject="Data Structures & Algorithms")
        session.add(track)
        await session.commit()
        await session.refresh(track)

        session.add(InterviewBrief(track_id=track.id, version=1, content={"summary": "v1"}))
        await session.commit()
        session.add(InterviewBrief(track_id=track.id, version=2, content={"summary": "v2"}))
        await session.commit()

        briefs = (
            (
                await session.execute(
                    InterviewBrief.__table__.select().where(InterviewBrief.track_id == track.id)
                )
            )
            .mappings()
            .all()
        )
        assert [b["version"] for b in briefs] == [1, 2]
