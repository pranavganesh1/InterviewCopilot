"""Task 7: Strict/Guided mode validation and interviewer mode routing."""

import uuid

import httpx
import pytest

from app.agents.interviewer import system_prompt_for_mode
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.feedback import ProgressionState
from app.models.track import InterviewBrief, Track
from app.models.user import User


async def _seed(monkeypatch, *, guided_state: str = "LOCKED"):
    from app.agents.interviewer import TurnDecision

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"mode-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="OS")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "OS basics",
                    "competencies": [
                        {"name": "Scheduling", "description": "cpu", "importance": "core"}
                    ],
                    "question_areas": [{"topic": "Scheduling", "guidance": "RR vs SJF"}],
                },
            )
        )
        session.add(
            ProgressionState(
                track_id=track.id, strict_completed=3, guided_state=guided_state
            )
        )
        await session.commit()

    captured: dict = {}

    async def fake_turn(*args, **kwargs):
        payload = kwargs.get("payload") or (args[0] if args else {})
        captured["payload"] = payload
        return TurnDecision(
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            decision="next_area",
            next_question="Compare RR and SJF scheduling.",
            question_area="Scheduling",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    return user, create_access_token(str(user.id)), track.id, captured


@pytest.mark.asyncio
async def test_strict_mode_can_start(monkeypatch, clean_users_table):
    _user, token, track_id, captured = await _seed(monkeypatch, guided_state="LOCKED")
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "strict"},
            cookies={"ic_access": token},
        )
    assert r.status_code == 201
    assert r.json()["session"]["mode"] == "strict"
    assert captured["payload"]["mode"] == "strict"


@pytest.mark.asyncio
async def test_locked_user_cannot_start_guided(monkeypatch, clean_users_table):
    _user, token, track_id, _captured = await _seed(monkeypatch, guided_state="LOCKED")
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "guided"},
            cookies={"ic_access": token},
        )
    assert r.status_code == 403
    assert "locked" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unlocked_user_can_start_guided(monkeypatch, clean_users_table):
    _user, token, track_id, captured = await _seed(monkeypatch, guided_state="UNLOCKED")
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "guided"},
            cookies={"ic_access": token},
        )
    assert r.status_code == 201
    assert r.json()["session"]["mode"] == "guided"
    assert captured["payload"]["mode"] == "guided"


@pytest.mark.asyncio
async def test_invalid_mode_rejected(monkeypatch, clean_users_table):
    _user, token, track_id, _c = await _seed(monkeypatch)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions",
            json={"mode": "chaos"},
            cookies={"ic_access": token},
        )
    assert r.status_code == 422


def test_strict_prompt_forbids_assistance_guided_allows_coaching_path():
    strict = system_prompt_for_mode("strict").lower()
    guided = system_prompt_for_mode("guided").lower()
    assert "never put hints" in strict or "never give hints" in strict
    assert "evaluation fields" in strict
    assert "assistance" in guided or "coaching" in guided
    assert "never put hints" not in guided and "never give hints" not in guided
