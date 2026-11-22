"""Isolated: verify-first welcome and profile confirm gate (no auto project pick)."""

from __future__ import annotations

import uuid

import pytest

from app.services.preparation_goals import goals_intro_message, infer_candidate_background
from app.services.vault_service import build_verify_first_welcome


def test_goals_intro_never_names_a_project():
    summary = [
        {"category": "project", "title": "QCGNN", "details": {}},
        {"category": "project", "title": "Other App", "details": {}},
        {"category": "skill", "title": "Python", "details": {}},
    ]
    msg = goals_intro_message(summary)
    assert "QCGNN" not in msg
    assert "Other App" not in msg
    assert "Python" not in msg
    assert "What would you like to focus on" in msg
    assert "role" in msg.lower()


def test_verify_welcome_has_no_project_claim():
    msg = build_verify_first_welcome(
        sync_result={"counts": {"created": 2, "skipped": 1, "failed": 0}},
        item_count=3,
        mode="resume",
    )
    assert "I've gone through your resume" in msg
    assert "make sure everything looks right" in msg
    assert "Sync result" not in msg
    assert "Profile Vault" not in msg
    assert "caught my eye" not in msg.lower()
    assert "QCGNN" not in msg


def test_python_alone_does_not_force_computer_science():
    bg = infer_candidate_background([{"category": "skill", "title": "Python", "details": {}}])
    assert bg["field_family"] != "computer_science"


def test_cs_education_still_maps_computer_science():
    bg = infer_candidate_background(
        [
            {"category": "education", "title": "B.Tech Computer Science", "details": {}},
            {"category": "skill", "title": "Python", "details": {}},
        ]
    )
    assert bg["field_family"] == "computer_science"


@pytest.mark.asyncio
async def test_profile_confirm_enables_goals_intro(clean_users_table):
    from httpx import ASGITransport, AsyncClient

    from app.core.security import create_access_token
    from app.db.mongo import get_mongo_db
    from app.db.sqlalchemy import SessionFactory
    from app.main import create_app
    from app.models.user import User
    from app.models.vault import VaultItem
    from app.services import conversation_store

    async with SessionFactory() as session:
        user = User(
            google_sub=f"sub-{uuid.uuid4().hex}",
            email=f"verify-{uuid.uuid4().hex[:8]}@example.com",
        )
        session.add(user)
        await session.flush()
        session.add(
            VaultItem(
                user_id=user.id,
                category="project",
                title="QCGNN",
                details={},
                source="resume",
            )
        )
        await session.commit()
        await session.refresh(user)
        user_id = str(user.id)
        token = create_access_token(user_id)

    mongo = get_mongo_db()
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    await conversation_store.start_new_conversation(
        mongo,
        user_id,
        title="New chat",
        reason="new_chat",
        welcome=build_verify_first_welcome(mode="new_chat"),
        reset_coach=True,
        coach_patch={"profile_verified": False, "proceed_to_goals": False},
    )

    app = create_app()
    app.state.mongo_db = mongo
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        before = await client.get("/api/v1/onboarding/state", cookies={"ic_access": token})
        assert before.status_code == 200
        msgs_before = before.json()["messages"]
        assert all(
            "What would you like to focus on" not in (m.get("content") or "") for m in msgs_before
        )
        assert "QCGNN" not in (msgs_before[0].get("content") or "")

        confirmed = await client.post(
            "/api/v1/onboarding/profile/confirm",
            cookies={"ic_access": token},
            json={"confirmed": True},
        )
        assert confirmed.status_code == 200
        body = confirmed.json()
        assert body.get("profile_verified") is True
        assert any(
            "What would you like to focus on" in (m.get("content") or "")
            for m in body.get("messages") or []
        )
        assert all(
            "caught my eye" not in (m.get("content") or "").lower()
            for m in body.get("messages") or []
        )
        # Still must not auto-name QCGNN in goals intro.
        goals_msgs = [
            m["content"]
            for m in body["messages"]
            if "What would you like to focus on" in (m.get("content") or "")
        ]
        assert goals_msgs
        assert "QCGNN" not in goals_msgs[0]

    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
