import uuid

import httpx
import pytest

from app.agents.onboarding import ExtractedItem, OnboardingTurn, compute_profile_gaps
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User
from app.models.vault import VaultItem
from app.services.vault_service import (
    build_profile_review_message,
    find_near_duplicates,
    titles_equivalent,
    titles_similar,
    upsert_extracted_items,
)


def test_title_normalization_and_similarity():
    assert titles_equivalent("Music Database Management", "music database management system")
    assert titles_similar("Music Database Management", "Music Database Management System v2")
    assert not titles_equivalent("QCGNN", "Music Database")


def test_compute_profile_gaps_and_duplicates():
    summary = [
        {
            "category": "project",
            "title": "QCGNN",
            "missing_details": ["purpose", "technologies"],
        },
        {"category": "skill", "title": "Python", "missing_details": []},
    ]
    gaps = compute_profile_gaps(summary)
    assert gaps["missing_categories"] == ["education"]
    assert gaps["incomplete_projects"][0]["title"] == "QCGNN"

    items = [
        VaultItem(
            user_id=uuid.uuid4(),
            category="achievement",
            title="Model performance",
            details={},
            source="resume",
        ),
        VaultItem(
            user_id=uuid.uuid4(),
            category="achievement",
            title="Model performance award",
            details={},
            source="resume",
        ),
    ]
    # similar via containment after normalize? "model performance" in "model performance award"
    assert find_near_duplicates(items)


def test_profile_review_message_lists_sections():
    uid = uuid.uuid4()
    items = [
        VaultItem(user_id=uid, category="education", title="B.Tech CSE", details={}, source="resume"),
        VaultItem(user_id=uid, category="skill", title="Python", details={}, source="resume"),
        VaultItem(
            user_id=uid,
            category="project",
            title="QCGNN",
            details={},
            source="resume",
        ),
    ]
    msg = build_profile_review_message(items)
    assert "Education" in msg and "QCGNN" in msg
    assert "purpose" in msg.lower() or "deepen" in msg.lower()


@pytest.mark.asyncio
async def test_upsert_merges_equivalent_titles(clean_users_table):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"u-{uuid.uuid4()}@ex.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        created, _ = await upsert_extracted_items(
            session,
            user.id,
            [ExtractedItem(category="project", title="Music DB", details={"purpose": "songs"})],
            "onboarding_chat",
        )
        assert len(created) == 1

        created2, updated2 = await upsert_extracted_items(
            session,
            user.id,
            [
                ExtractedItem(
                    category="project",
                    title="Music DB System",
                    details={"technologies": "MySQL"},
                )
            ],
            "onboarding_chat",
        )
        assert created2 == []
        assert len(updated2) == 1
        assert updated2[0].details["purpose"] == "songs"
        assert updated2[0].details["technologies"] == "MySQL"


@pytest.mark.asyncio
async def test_state_prefills_review_when_vault_exists(clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client

    email = f"pre-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        session.add(
            VaultItem(
                user_id=user.id,
                category="project",
                title="QCGNN",
                details={"technologies": "PyTorch"},
                source="resume",
            )
        )
        session.add(
            VaultItem(
                user_id=user.id,
                category="skill",
                title="Python",
                details={},
                source="resume",
            )
        )
        session.add(
            VaultItem(
                user_id=user.id,
                category="education",
                title="B.Tech",
                details={},
                source="resume",
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    mongo = get_mongo_client()[get_settings().mongo_db]
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})

    app = create_app()
    app.state.mongo_db = mongo
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/onboarding/state", cookies={"ic_access": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["vault_items"][0]["details"]
    assert any(m["role"] == "assistant" for m in body["messages"])
    assert "QCGNN" in body["messages"][0]["content"]

    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_chat_upserts_instead_of_duplicating(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client
    from sqlalchemy import select

    email = f"dup-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        session.add(
            VaultItem(
                user_id=user.id,
                category="project",
                title="Line follower",
                details={"purpose": "navigate"},
                source="resume",
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = user.id

    turn = OnboardingTurn(
        reply="Which sensors did you use?",
        extracted_items=[
            ExtractedItem(
                category="project",
                title="Line Follower",  # equivalent title → merge details
                details={"technologies": "Arduino IR"},
            )
        ],
    )

    async def fake_turn(*args, **kwargs):
        return turn

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", fake_turn)

    app = create_app()
    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "Arduino IR sensors"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items_created"] == []
    assert body["items_updated"][0]["title"]

    async with SessionFactory() as session:
        items = (
            (await session.execute(select(VaultItem).where(VaultItem.user_id == user_id)))
            .scalars()
            .all()
        )
        assert len(items) == 1
        assert items[0].details.get("purpose") == "navigate"
        assert items[0].details.get("technologies") == "Arduino IR"

    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": str(user_id)})
