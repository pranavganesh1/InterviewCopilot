import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.track import InterviewBrief, Track
from app.models.user import User


async def _setup_track_with_brief(monkeypatch):
    from app.agents.interviewer import TurnDecision

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"iv-{uuid.uuid4()}@example.com")
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
                    "summary": "DSA basics",
                    "competencies": [
                        {"name": "Arrays", "description": "arrays", "importance": "core"}
                    ],
                    "question_areas": [
                        {"topic": "Hashmaps", "guidance": "collisions"},
                        {"topic": "Big-O", "guidance": "complexity analysis"},
                    ],
                },
            )
        )
        await session.commit()
    token = create_access_token(str(user.id))

    async def fake_turn(*args, **kwargs):
        payload = kwargs.get("payload") or (args[0] if args else {})
        transcript = payload.get("transcript", [])
        last_area = transcript[-1]["area"] if transcript else None
        turns_in_area = payload.get("turns_in_current_area", 0)

        if last_area is None:
            return TurnDecision(
                evaluation={"coverage": "none", "strengths": [], "gaps": []},
                decision="next_area",
                next_question="Explain hashmaps and collisions.",
                question_area="Hashmaps",
            )
        if last_area == "Hashmaps":
            if turns_in_area >= 2:  # question + one follow-up already asked
                return TurnDecision(
                    evaluation={"coverage": "good", "strengths": ["clear"], "gaps": []},
                    decision="next_area",
                    next_question="What is Big-O of a hashmap lookup?",
                    question_area="Big-O",
                )
            return TurnDecision(
                evaluation={"coverage": "partial", "strengths": ["ok"], "gaps": ["collisions"]},
                decision="follow_up",
                next_question="How would you handle collisions?",
                question_area="Hashmaps",
            )
        return TurnDecision(  # Big-O answered -> done
            evaluation={"coverage": "good", "strengths": ["concise"], "gaps": []},
            decision="complete",
            next_question="",
            question_area="Big-O",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    return user, token, track.id


@pytest.mark.asyncio
async def test_full_strict_interview_flow(monkeypatch, clean_users_table):
    user, token, track_id = await _setup_track_with_brief(monkeypatch)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token})
        assert r.status_code == 201
        sid = r.json()["session"]["id"]
        assert r.json()["turn"]["question"].startswith("Explain hashmaps")

        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "A hashmap maps keys to buckets..."},
            cookies={"ic_access": token},
        )
        assert r.json()["completed"] is False
        assert r.json()["turn"]["question"].startswith("How would you handle")

        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "Chaining or open addressing..."},
            cookies={"ic_access": token},
        )
        assert r.json()["completed"] is False
        assert r.json()["turn"]["question"].startswith("What is Big-O")

        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "O(1) average case..."},
            cookies={"ic_access": token},
        )
        assert r.json()["completed"] is True

        r = await client.get(f"/api/v1/sessions/{sid}", cookies={"ic_access": token})
        body = r.json()
        assert body["session"]["status"] == "completed"
        assert len(body["turns"]) == 3
        assert body["turns"][0]["answer"] == "A hashmap maps keys to buckets..."


@pytest.mark.asyncio
async def test_session_recovers_after_restart(monkeypatch, clean_users_table):
    user, token, track_id = await _setup_track_with_brief(monkeypatch)
    app1 = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app1), base_url="http://t") as c:
        r = await c.post(f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token})
        sid = r.json()["session"]["id"]
        await c.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "buckets and hashing"},
            cookies={"ic_access": token},
        )
    app2 = create_app()  # "restart": fresh app instance, state comes from DB rows
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://t") as c:
        r = await c.get(f"/api/v1/sessions/{sid}", cookies={"ic_access": token})
        assert r.status_code == 200
        body = r.json()
        # turn 1 answered; turn 2 (the follow-up question) was pre-loaded before the crash
        assert len(body["turns"]) == 2
        assert body["turns"][0]["answer"] == "buckets and hashing"
        assert body["turns"][1]["answer"] is None
        assert body["session"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_sessions_require_auth():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/v1/sessions/{uuid.uuid4()}")
    assert r.status_code == 401
