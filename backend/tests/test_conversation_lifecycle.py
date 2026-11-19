"""Isolated tests: resume upload starts a fresh conversation; history is preserved."""

from __future__ import annotations

import uuid

import pytest

from app.main import create_app
from app.services import conversation_store, onboarding_service
from app.services.vault_service import build_resume_sync_welcome


@pytest.fixture
async def mongo_user(clean_users_table):
    from app.db.mongo import get_mongo_db
    from app.db.sqlalchemy import SessionFactory
    from app.models.user import User

    async with SessionFactory() as session:
        user = User(
            google_sub=f"sub-{uuid.uuid4().hex}",
            email=f"life-{uuid.uuid4().hex[:8]}@example.com",
            name="Lifecycle Tester",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = str(user.id)

    mongo = get_mongo_db()
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    yield {"user_id": user_id, "mongo": mongo, "user": user}
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_build_resume_sync_welcome_uses_real_counts():
    text = build_resume_sync_welcome(
        {
            "counts": {
                "created": 2,
                "skipped": 3,
                "enrichment_candidates": 1,
                "uncertain_matches": 0,
                "failed": 0,
            }
        },
        items=[object()],
    )
    assert "I've gone through your resume" in text
    assert "make sure everything looks right" in text
    assert "Sync result" not in text
    assert "Profile Vault" not in text
    assert "created" not in text.lower() or "updated your profile" in text
    assert "caught my eye" not in text.lower()


@pytest.mark.asyncio
async def test_build_resume_sync_welcome_failed_only():
    text = build_resume_sync_welcome(
        {"counts": {"created": 0, "skipped": 0, "failed": 2}},
        items=[],
    )
    assert "wasn't able" in text.lower() or "couldn't" in text.lower()
    assert "Sync result" not in text
    assert "2 failed" not in text


@pytest.mark.asyncio
async def test_resume_seed_archives_prior_and_starts_fresh(mongo_user):
    mongo = mongo_user["mongo"]
    user_id = mongo_user["user_id"]

    await conversation_store.append_message(mongo, user_id, "user", "Old hello")
    await conversation_store.append_message(
        mongo, user_id, "assistant", "Old coach reply about prior chat"
    )
    prior = await conversation_store.get_active_conversation_meta(mongo, user_id)
    prior_id = prior["conversation_id"]

    class _Item:
        category = "skill"
        title = "Python"
        details = {}

    seeded = await onboarding_service.seed_resume_welcome(
        mongo,
        user_id,
        [_Item()],
        sync_result={
            "counts": {
                "created": 1,
                "skipped": 4,
                "enrichment_candidates": 0,
                "uncertain_matches": 0,
                "failed": 0,
            },
            "items_created": [{"id": "x", "category": "skill", "title": "Python"}],
        },
    )
    assert seeded["seeded"] is True
    assert seeded["conversation_id"] != prior_id

    active_msgs = await conversation_store.get_messages(mongo, user_id, limit=50)
    assert len(active_msgs) == 1
    assert active_msgs[0]["role"] == "assistant"
    assert "I've gone through your resume" in active_msgs[0]["content"]
    assert "make sure everything looks right" in active_msgs[0]["content"]
    assert "Sync result" not in active_msgs[0]["content"]
    assert "Old hello" not in active_msgs[0]["content"]

    summaries = await conversation_store.list_conversation_summaries(mongo, user_id)
    assert len(summaries) >= 2
    archived = [s for s in summaries if not s.get("active")]
    assert any(s["id"] == prior_id for s in archived)

    # Idempotent: second seed against fresh resume thread is a no-op.
    again = await onboarding_service.seed_resume_welcome(
        mongo, user_id, [_Item()], sync_result={"counts": {"created": 1, "skipped": 0}}
    )
    assert again["seeded"] is False
    assert again["conversation_id"] == seeded["conversation_id"]


@pytest.mark.asyncio
async def test_switch_conversations_restores_messages(mongo_user):
    mongo = mongo_user["mongo"]
    user_id = mongo_user["user_id"]

    await conversation_store.append_message(mongo, user_id, "user", "Thread A message")
    first = await conversation_store.get_active_conversation_meta(mongo, user_id)
    first_id = first["conversation_id"]

    started = await conversation_store.start_new_conversation(
        mongo,
        user_id,
        title="Thread B",
        reason="new_chat",
        welcome="Welcome to thread B",
    )
    second_id = started["conversation_id"]
    assert second_id != first_id
    msgs_b = await conversation_store.get_messages(mongo, user_id)
    assert msgs_b[0]["content"] == "Welcome to thread B"
    assert all("Thread A message" not in (m.get("content") or "") for m in msgs_b)

    switched = await conversation_store.activate_conversation(mongo, user_id, first_id)
    assert switched and switched["switched"] is True
    msgs_a = await conversation_store.get_messages(mongo, user_id)
    assert any("Thread A message" in (m.get("content") or "") for m in msgs_a)
    assert all("Welcome to thread B" not in (m.get("content") or "") for m in msgs_a)

    # Other user's id cannot activate this conversation (owner scope via user_id filter).
    other = f"other-{uuid.uuid4()}"
    assert await conversation_store.activate_conversation(mongo, other, first_id) is None


@pytest.mark.asyncio
async def test_conversation_apis_owner_scoped(mongo_user, clean_users_table):
    from httpx import ASGITransport, AsyncClient

    from app.core.security import create_access_token
    from app.db.sqlalchemy import SessionFactory
    from app.models.user import User

    mongo = mongo_user["mongo"]
    user_id = mongo_user["user_id"]
    await conversation_store.append_message(mongo, user_id, "user", "Keep me")
    token = create_access_token(user_id)

    app = create_app()
    app.state.mongo_db = mongo
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await client.get(
            "/api/v1/onboarding/conversations",
            cookies={"ic_access": token},
        )
        assert listed.status_code == 200
        assert listed.json()["count"] >= 1

        created = await client.post(
            "/api/v1/onboarding/conversations",
            cookies={"ic_access": token},
        )
        assert created.status_code == 200
        body = created.json()
        assert body.get("conversation_id")
        assert len(body.get("messages") or []) == 1
        welcome = body["messages"][0].get("content") or ""
        assert "Ready when you are" in welcome or "Welcome back" in welcome
        assert "Profile Vault" not in welcome
        assert "QCGNN" not in welcome
        assert "caught my eye" not in welcome.lower()
        # Prior message archived — not in active messages.
        assert all("Keep me" not in (m.get("content") or "") for m in body["messages"])

        archived = [c for c in body["conversations"] if not c.get("active")]
        assert archived
        switched = await client.post(
            "/api/v1/onboarding/conversations/activate",
            cookies={"ic_access": token},
            json={"conversation_id": archived[0]["id"]},
        )
        assert switched.status_code == 200
        restored = switched.json()["messages"]
        assert any("Keep me" in (m.get("content") or "") for m in restored)

        # Foreign user cannot activate.
        async with SessionFactory() as session:
            other = User(
                google_sub=f"sub-{uuid.uuid4().hex}",
                email=f"other-{uuid.uuid4().hex[:8]}@example.com",
            )
            session.add(other)
            await session.commit()
            await session.refresh(other)
            other_token = create_access_token(str(other.id))
        denied = await client.post(
            "/api/v1/onboarding/conversations/activate",
            cookies={"ic_access": other_token},
            json={"conversation_id": archived[0]["id"]},
        )
        assert denied.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_removes_messages_persistently(mongo_user):
    mongo = mongo_user["mongo"]
    user_id = mongo_user["user_id"]

    await conversation_store.append_message(mongo, user_id, "user", "Archive me")
    first = await conversation_store.get_active_conversation_meta(mongo, user_id)
    first_id = first["conversation_id"]

    await conversation_store.start_new_conversation(
        mongo,
        user_id,
        title="Keep this",
        reason="new_chat",
        welcome="Stay active",
    )
    active = await conversation_store.get_active_conversation_meta(mongo, user_id)
    active_id = active["conversation_id"]
    assert active_id != first_id

    deleted = await conversation_store.delete_conversation(mongo, user_id, first_id)
    assert deleted is not None
    assert deleted["deleted_id"] == first_id
    assert deleted["deleted_active"] is False
    assert deleted["messages_removed"] >= 1

    summaries = await conversation_store.list_conversation_summaries(mongo, user_id)
    ids = {s["id"] for s in summaries}
    assert first_id not in ids
    assert active_id in ids

    msgs = await conversation_store.get_messages(mongo, user_id)
    assert any("Stay active" in (m.get("content") or "") for m in msgs)
    assert all("Archive me" not in (m.get("content") or "") for m in msgs)

    # Already deleted → None (safe idempotent miss).
    assert await conversation_store.delete_conversation(mongo, user_id, first_id) is None

    # Other user cannot delete this user's conversation.
    assert (
        await conversation_store.delete_conversation(
            mongo, f"other-{uuid.uuid4()}", active_id
        )
        is None
    )


@pytest.mark.asyncio
async def test_delete_active_promotes_archive_and_preserves_vault(
    mongo_user, clean_users_table
):
    from httpx import ASGITransport, AsyncClient

    from app.core.security import create_access_token
    from app.db.sqlalchemy import SessionFactory
    from app.models.user import User
    from app.models.vault import VaultItem
    from app.services.vault_service import list_items

    mongo = mongo_user["mongo"]
    user_id = mongo_user["user_id"]
    user = mongo_user["user"]

    async with SessionFactory() as session:
        session.add(
            VaultItem(
                user_id=user.id,
                category="skill",
                title="Python",
                details={},
                source="resume",
            )
        )
        await session.commit()
        vault_before = await list_items(session, user.id)
    assert any(i.title == "Python" for i in vault_before)

    await conversation_store.append_message(mongo, user_id, "user", "Old thread")
    old = await conversation_store.get_active_conversation_meta(mongo, user_id)
    old_id = old["conversation_id"]
    started = await conversation_store.start_new_conversation(
        mongo, user_id, title="Active", reason="new_chat", welcome="Active welcome"
    )
    active_id = started["conversation_id"]

    token = create_access_token(user_id)
    app = create_app()
    app.state.mongo_db = mongo
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(
            f"/api/v1/onboarding/conversations/{active_id}",
            cookies={"ic_access": token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["conversation_deleted"]["deleted_id"] == active_id
        # Active chat messages gone; archived old thread may be promoted.
        assert all(
            "Active welcome" not in (m.get("content") or "")
            for m in body.get("messages") or []
        )
        listed = await client.get(
            "/api/v1/onboarding/conversations",
            cookies={"ic_access": token},
        )
        ids = {c["id"] for c in listed.json()["conversations"]}
        assert active_id not in ids
        assert old_id in ids

        # Idempotent second delete → 404
        again = await client.delete(
            f"/api/v1/onboarding/conversations/{active_id}",
            cookies={"ic_access": token},
        )
        assert again.status_code == 404

        # Foreign candidate cannot delete remaining conversation.
        async with SessionFactory() as session:
            other = User(
                google_sub=f"sub-{uuid.uuid4().hex}",
                email=f"other-{uuid.uuid4().hex[:8]}@example.com",
            )
            session.add(other)
            await session.commit()
            await session.refresh(other)
            other_token = create_access_token(str(other.id))
        foreign = await client.delete(
            f"/api/v1/onboarding/conversations/{old_id}",
            cookies={"ic_access": other_token},
        )
        assert foreign.status_code == 404

    async with SessionFactory() as session:
        vault_after = await list_items(session, user.id)
    assert any(i.title == "Python" for i in vault_after)
    assert len(vault_after) == len(vault_before)
