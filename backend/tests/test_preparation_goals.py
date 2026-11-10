import uuid

import httpx
import pytest

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.mongo import get_mongo_client
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User
from app.models.vault import VaultItem
from app.services.preparation_goals import (
    merge_preferences,
    recommend_track_seeds,
    preferences_ready,
)


def test_merge_and_recommend():
    prefs = merge_preferences(
        None,
        {
            "interests": ["skill", "project"],
            "focus_skills": ["Python", "SQL"],
            "focus_projects": ["QCGNN"],
            "confirmed": True,
        },
    )
    assert preferences_ready(prefs)
    seeds = recommend_track_seeds(prefs)
    subjects = [s["subject"] for s in seeds]
    assert "Python" in subjects
    assert any("QCGNN" in s for s in subjects)


@pytest.mark.asyncio
async def test_goals_endpoint_and_complete(monkeypatch, clean_users_table):
    from app.agents.onboarding import OnboardingTurn

    email = f"goal-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        for cat, title in (
            ("project", "QCGNN"),
            ("skill", "Python"),
            ("education", "B.Tech"),
        ):
            session.add(
                VaultItem(
                    user_id=user.id,
                    category=cat,
                    title=title,
                    details={},
                    source="resume",
                )
            )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    async def fake_turn(*args, **kwargs):
        return OnboardingTurn(
            reply="Which skills should we practice first?",
            phase="goals",
            show_goal_menu=False,
            preparation_update=None,
        )

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", fake_turn)

    app = create_app()
    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        blocked = await client.post(
            "/api/v1/onboarding/complete",
            cookies={"ic_access": token},
        )
        assert blocked.status_code == 409

        goals = await client.post(
            "/api/v1/onboarding/goals",
            json={"interests": ["skill", "technical"], "focus_skills": ["Python"]},
            cookies={"ic_access": token},
        )
        assert goals.status_code == 200
        body = goals.json()
        assert "skill" in body["preparation_preferences"]["interests"]
        assert body["phase"] in ("goals", "ready")

        state = await client.get("/api/v1/onboarding/state", cookies={"ic_access": token})
        assert state.status_code == 200
        assert state.json()["show_goal_menu"] is False or state.json()["preparation_preferences"][
            "interests"
        ]

        done = await client.post(
            "/api/v1/onboarding/complete",
            cookies={"ic_access": token},
        )
        assert done.status_code == 200
        assert done.json()["onboarding_finished"] is True
        assert done.json()["preparation_preferences"]["confirmed"] is True

        me = await client.get("/api/v1/auth/me", cookies={"ic_access": token})
        assert me.status_code == 200
        assert me.json()["preparation_preferences"]["interests"]
        assert me.json()["recommended_tracks"]

    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
