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
    GOALS_INTRO_MARKER,
    build_resume_goal_options,
    followups_complete,
    goals_followup_reply,
    goals_intro_message,
    merge_preferences,
    next_goal_followup,
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


def test_resume_goal_options_and_followups():
    summary = [
        {
            "category": "skill",
            "title": "Python",
            "details": {},
        },
        {
            "category": "skill",
            "title": "SQL",
            "details": {},
        },
        {
            "category": "project",
            "title": "QCGNN",
            "details": {
                "technologies": "quantum computing, graph neural networks, Python",
                "purpose": "research prototype",
            },
        },
        {"category": "education", "title": "B.Tech CSE", "details": {}},
        {"category": "internship", "title": "ML Intern", "details": {}},
    ]
    opts = build_resume_goal_options(summary)
    assert "Python" in opts["suggested_skills"]
    assert "QCGNN" in opts["suggested_projects"]
    assert any(p["label"] == "QCGNN" for p in opts["project_options"])
    assert "ML Intern" in opts["suggested_roles"]
    assert opts["project_aspect_options"]
    assert GOALS_INTRO_MARKER in goals_intro_message(summary)
    assert "QCGNN" in goals_intro_message(summary)

    prefs = merge_preferences(None, {"interests": ["project"]})
    reply = goals_followup_reply(prefs, summary)
    assert "QCGNN" in reply
    assert next_goal_followup(prefs) == "projects"
    assert followups_complete(prefs) is False

    prefs = merge_preferences(
        prefs, {"focus_projects": ["QCGNN"], "project_aspects": []}
    )
    reply2 = goals_followup_reply(prefs, summary)
    assert "architecture" in reply2.lower() or "challenges" in reply2.lower()
    assert next_goal_followup(prefs) == "project_aspects"

    prefs = merge_preferences(prefs, {"project_aspects": ["architecture"]})
    assert next_goal_followup(prefs) is None
    assert followups_complete(prefs) is True


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
