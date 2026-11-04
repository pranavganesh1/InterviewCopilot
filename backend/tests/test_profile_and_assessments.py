"""Profile PATCH and assessments dashboard."""

import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.models.track import Track
from app.models.user import User
from app.services.feedback_service import overall_score_from_content


def test_overall_score_averages_coverage_only():
    assert overall_score_from_content({"question_assessments": []}) is None
    score = overall_score_from_content(
        {
            "question_assessments": [
                {"coverage": "excellent"},
                {"coverage": "partial"},
            ]
        }
    )
    assert score == 75


@pytest.mark.asyncio
async def test_patch_profile_and_me(clean_users_table):
    async with SessionFactory() as session:
        user = User(
            google_sub=f"sub-{uuid.uuid4()}",
            email=f"p-{uuid.uuid4()}@example.com",
            name="Old Name",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        me = await client.get("/api/v1/auth/me", cookies={"ic_access": token})
        assert me.status_code == 200
        assert me.json()["name"] == "Old Name"
        assert me.json()["skills"] == []

        patched = await client.patch(
            "/api/v1/auth/me",
            cookies={"ic_access": token},
            json={
                "name": "Kushal Nayak",
                "professional_title": "Backend Engineer",
                "introduction": "Building interview copilots.",
                "skills": ["Python", "FastAPI"],
                "education": "B.Tech CSE",
            },
        )
        assert patched.status_code == 200
        body = patched.json()
        assert body["name"] == "Kushal Nayak"
        assert body["professional_title"] == "Backend Engineer"
        assert body["skills"] == ["Python", "FastAPI"]
        assert body["education"] == "B.Tech CSE"

        me2 = await client.get("/api/v1/auth/me", cookies={"ic_access": token})
        assert me2.json()["professional_title"] == "Backend Engineer"


@pytest.mark.asyncio
async def test_assessments_dashboard_lists_own_reports_only(clean_users_table):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"a-{uuid.uuid4()}@example.com")
        other = User(google_sub=f"sub-{uuid.uuid4()}", email=f"o-{uuid.uuid4()}@example.com")
        session.add_all([user, other])
        await session.commit()
        await session.refresh(user)
        await session.refresh(other)

        track = Track(user_id=user.id, track_type="topic", subject="Systems")
        session.add(track)
        await session.commit()
        await session.refresh(track)

        sess = InterviewSession(
            track_id=track.id, user_id=user.id, mode="strict", status="completed"
        )
        session.add(sess)
        await session.commit()
        await session.refresh(sess)

        session.add(
            FeedbackReport(
                session_id=sess.id,
                track_id=track.id,
                user_id=user.id,
                content={
                    "report_version": 1,
                    "session_mode": "strict",
                    "summary_overview": "Solid basics.",
                    "coverage_status": "PARTIAL",
                    "question_assessments": [
                        {
                            "turn_index": 1,
                            "coverage": "good",
                            "observation": "ok",
                            "evidence_excerpt": "",
                        }
                    ],
                    "competency_assessments": [
                        {
                            "competency_name": "Networking",
                            "assessment_status": "ASSESSED",
                            "level": "solid",
                            "observation": "",
                            "confidence": "MEDIUM",
                        }
                    ],
                    "strengths": ["Clear explanations"],
                    "improvement_areas": ["Add examples"],
                    "unassessed_topics": [],
                    "recommendations": ["Practice TCP handshake"],
                },
            )
        )
        # Report belonging to someone else must not appear.
        other_track = Track(user_id=other.id, track_type="topic", subject="Hidden")
        session.add(other_track)
        await session.commit()
        await session.refresh(other_track)
        other_sess = InterviewSession(
            track_id=other_track.id, user_id=other.id, mode="strict", status="completed"
        )
        session.add(other_sess)
        await session.commit()
        await session.refresh(other_sess)
        session.add(
            FeedbackReport(
                session_id=other_sess.id,
                track_id=other_track.id,
                user_id=other.id,
                content={
                    "report_version": 1,
                    "session_mode": "strict",
                    "summary_overview": "secret",
                    "coverage_status": "COMPLETE",
                    "question_assessments": [],
                    "competency_assessments": [],
                    "strengths": [],
                    "improvement_areas": [],
                    "unassessed_topics": [],
                    "recommendations": [],
                },
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/me/assessments", cookies={"ic_access": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["dashboard"]["completed_interviews"] == 1
    assert body["dashboard"]["average_score"] == 75
    assert body["dashboard"]["total_questions_attempted"] == 1
    assert len(body["assessments"]) == 1
    assert body["assessments"][0]["track_subject"] == "Systems"
    assert "Hidden" not in [a["track_subject"] for a in body["assessments"]]
