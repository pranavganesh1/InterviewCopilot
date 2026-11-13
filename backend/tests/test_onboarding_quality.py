import uuid

import httpx
import pytest

from app.agents.onboarding import (
    ExtractedItem,
    OnboardingTurn,
    ack_followup_question,
    classify_duplicate_answer,
    classify_practise_intent,
    compute_profile_gaps,
    ensure_nonempty_reply,
    is_ack_only,
)
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
    from app.services.vault_service import (
        RESUME_WELCOME_MARKER,
        message_looks_like_resume_welcome,
    )

    uid = uuid.uuid4()
    items = [
        VaultItem(
            user_id=uid,
            category="education",
            title="B.Tech CSE",
            details={},
            source="resume",
        ),
        VaultItem(
            user_id=uid,
            category="skill",
            title="Python",
            details={},
            source="resume",
        ),
        VaultItem(
            user_id=uid,
            category="project",
            title="QCGNN",
            details={},
            source="resume",
        ),
    ]
    msg = build_profile_review_message(items)
    assert RESUME_WELCOME_MARKER in msg
    assert "QCGNN" in msg
    # Warm coach tone: highlight a couple of items, not a full resume dump.
    assert "and 11 more" not in msg
    assert "I found your experience in" not in msg
    assert "goals" in msg.lower() or "work on" in msg.lower()
    assert message_looks_like_resume_welcome(msg)
    assert not message_looks_like_resume_welcome("Just a normal coach reply")


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
        assert body["has_resume_welcome"] is True
        assert body["show_starters"] is True
        assert any(s["id"] == "ai_interview" for s in body["conversation_starters"])
        # Welcome must not mark onboarding finished.
        assert body["onboarding_finished"] is False

        # Refresh must not duplicate the welcome.
        again = await client.get("/api/v1/onboarding/state", cookies={"ic_access": token})
        assert again.status_code == 200
        welcomes = [
            m
            for m in again.json()["messages"]
            if m["role"] == "assistant" and "I've reviewed your resume" in m["content"]
        ]
        assert len(welcomes) == 1

    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_seed_resume_welcome_is_idempotent(clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client
    from app.services import conversation_store, onboarding_service
    from app.services.vault_service import list_items

    email = f"seed-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        session.add_all(
            [
                VaultItem(
                    user_id=user.id,
                    category="skill",
                    title="Java",
                    details={},
                    source="resume",
                ),
                VaultItem(
                    user_id=user.id,
                    category="project",
                    title="Portfolio",
                    details={},
                    source="resume",
                ),
            ]
        )
        await session.commit()
        user_id = str(user.id)
        vault_items = await list_items(session, user.id)

    mongo = get_mongo_client()[get_settings().mongo_db]
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})

    first = await onboarding_service.seed_resume_welcome(mongo, user_id, vault_items)
    second = await onboarding_service.seed_resume_welcome(mongo, user_id, vault_items)
    assert first is True
    assert second is False
    messages = await conversation_store.get_messages(mongo, user_id, limit=40)
    assert sum(1 for m in messages if "I've reviewed your resume" in m["content"]) == 1
    assert "Portfolio" in messages[0]["content"]
    # Warm welcome highlights a project — not a full skill dump.
    assert "I found your experience in" not in messages[0]["content"]

    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_conversation_starter_sets_mode_and_chats(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client
    from app.services import conversation_store

    email = f"start-{uuid.uuid4()}@example.com"
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

    turn = OnboardingTurn(
        reply="Thanks — what's one technical decision you made on QCGNN?",
        extracted_items=[],
        phase="profile",
    )

    async def fake_turn(*args, **kwargs):
        assert kwargs.get("conversation_mode") == "ai_interview"
        return turn

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", fake_turn)

    mongo = get_mongo_client()[get_settings().mongo_db]
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})

    app = create_app()
    app.state.mongo_db = mongo
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed welcome via state first.
        await client.get("/api/v1/onboarding/state", cookies={"ic_access": token})
        resp = await client.post(
            "/api/v1/onboarding/starter",
            json={"starter_id": "ai_interview"},
            cookies={"ic_access": token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "QCGNN" in body["reply"] or "technical" in body["reply"].lower()
        assert body["conversation_mode"] == "ai_interview"
        assert body["onboarding_complete"] is False or body.get("phase") != "ready"

        bad = await client.post(
            "/api/v1/onboarding/starter",
            json={"starter_id": "not_a_real_starter"},
            cookies={"ic_access": token},
        )
        assert bad.status_code == 422

    mode = await conversation_store.get_conversation_mode(mongo, user_id)
    assert mode == "ai_interview"
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_chat_upserts_instead_of_duplicating(monkeypatch, clean_users_table):
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client

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

def test_ensure_nonempty_and_ack_helpers():
    assert ensure_nonempty_reply("") 
    assert "What" in ensure_nonempty_reply("", vault_summary=[
        {"category": "project", "title": "DBMS", "details": {}}
    ]) or "How" in ensure_nonempty_reply("", vault_summary=[
        {"category": "project", "title": "DBMS", "details": {}}
    ])
    assert classify_duplicate_answer("give both") == "keep_both"
    assert classify_duplicate_answer("keep both") == "keep_both"
    assert classify_duplicate_answer("same") == "merge"
    assert classify_duplicate_answer("merge") == "merge"
    assert is_ack_only("lets us start")
    assert is_ack_only("ok")
    assert not is_ack_only("I built a DBMS project with MySQL")
    q = ack_followup_question([{"category": "skill", "title": "Excel", "details": {}}])
    assert q.strip()
    assert q[0].isupper()
    practise = classify_practise_intent(
        "I'd like to practise Python",
        [{"category": "skill", "title": "Python", "details": {}}],
    )
    assert practise and practise["subject"] == "Python"

    from app.agents.onboarding import (
        classify_topic_focus,
        continue_topic_reply,
        is_affirmative,
        resolve_topic_confirmation,
        topic_focus_reply,
        wants_topic_switch,
    )

    vault = [
        {
            "category": "project",
            "title": "Music Database Management",
            "details": {"purpose": "store songs", "technologies": "MySQL, Flask"},
        },
        {
            "category": "project",
            "title": "QCGNN",
            "details": {"purpose": "quantum graphs", "technologies": "PyTorch"},
        },
        {
            "category": "skill",
            "title": "Python",
            "details": {"level": "intermediate"},
        },
    ]
    focused = classify_topic_focus("I want in DBMS project", vault)
    assert focused is not None
    assert focused["title"] == "Music Database Management"
    reply = topic_focus_reply(focused)
    assert "Music Database Management" in reply
    assert "Machine Learning" not in reply
    assert "QCGNN" not in reply
    assert classify_topic_focus("tell me a joke", vault) is None
    assert classify_topic_focus("yes", vault) is None
    assert is_affirmative("yes")

    skill = classify_topic_focus("I want to discuss my Python skill", vault)
    assert skill and skill["title"] == "Python" and skill["kind"] == "skill"

    ml = classify_topic_focus("switch to my QCGNN project", vault)
    assert ml and ml["title"] == "QCGNN"
    assert wants_topic_switch("let's talk about something else")

    locked_ctx = {
        "current_topic": "Music Database Management",
        "focus_kind": "project",
        "focus_locked": True,
        "last_question_intent": "explore",
    }
    cont = continue_topic_reply(locked_ctx, vault)
    assert cont and "Music Database Management" in cont
    assert "QCGNN" not in cont

    confirm = resolve_topic_confirmation(
        "yes",
        vault,
        {
            "last_question_intent": "confirm_topic",
            "pending_followup": "Music Database Management",
        },
    )
    assert confirm and confirm["title"] == "Music Database Management"

    # Already locked on that topic — do not restart the opening confirmation.
    assert (
        resolve_topic_confirmation(
            "yes",
            vault,
            {
                "last_question_intent": "confirm_topic",
                "pending_followup": "Music Database Management",
                "current_topic": "Music Database Management",
                "focus_locked": True,
            },
        )
        is None
    )

    from app.agents.onboarding import infer_question_intent

    assert infer_question_intent(
        "What did you focus on most in your Physics lab?"
    ) == "explore"
    assert infer_question_intent(
        "Would you like to discuss your Accounting project next?"
    ) == "confirm_topic"


@pytest.mark.asyncio
async def test_chat_never_returns_empty_reply(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client

    email = f"empty-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    async def blank_turn(*args, **kwargs):
        return OnboardingTurn(reply="", extracted_items=[], phase="profile")

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", blank_turn)

    app = create_app()
    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "Hello coach"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    assert resp.json()["reply"].strip()
    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_give_both_resolves_duplicate(monkeypatch, clean_users_table):
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client
    from app.services import conversation_store

    email = f"both-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        session.add(
            VaultItem(
                user_id=user.id,
                category="education",
                title="PES University",
                details={},
                source="resume",
            )
        )
        session.add(
            VaultItem(
                user_id=user.id,
                category="education",
                title="PES University BTech",
                details={},
                source="resume",
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    async def should_not_run(*args, **kwargs):
        raise AssertionError("LLM should not run for give both")

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", should_not_run)

    app = create_app()
    mongo = get_mongo_client()[get_settings().mongo_db]
    app.state.mongo_db = mongo
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    await conversation_store.append_message(
        mongo,
        user_id,
        "assistant",
        "I also noticed two similar education entries - same item, or keep both?",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "give both"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"].strip()
    assert "both" in body["reply"].lower() or "Kept" in body["reply"]

    async with SessionFactory() as session:
        items = (
            (
                await session.execute(
                    select(VaultItem).where(VaultItem.user_id == uuid.UUID(user_id))
                )
            )
            .scalars()
            .all()
        )
        assert len(items) == 2

    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_ack_only_gets_specific_question(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client

    email = f"ack-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
        session.add(
            VaultItem(
                user_id=user.id,
                category="project",
                title="Music DB",
                details={},
                source="resume",
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    async def should_not_run(*args, **kwargs):
        raise AssertionError("LLM should not run for ack-only")

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", should_not_run)

    app = create_app()
    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "lets us start"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    assert reply.strip()
    assert reply.lstrip().startswith(("What", "How", "Which"))
    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_llm_quota_returns_503_and_keeps_user_message(
    monkeypatch, clean_users_table
):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client
    from app.gateway.llm import LLMGatewayError
    from app.services import conversation_store

    email = f"quota-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    async def boom(*args, **kwargs):
        raise LLMGatewayError("quota")

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", boom)

    app = create_app()
    mongo = get_mongo_client()[get_settings().mongo_db]
    app.state.mongo_db = mongo
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "Tell me about interviews"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    detail_text = detail if isinstance(detail, str) else str(detail.get("message", ""))
    assert "retry" in detail_text.lower()
    msgs = await conversation_store.get_messages(mongo, user_id, limit=10)
    assert any(
        m.get("role") == "user" and "Tell me about interviews" in m.get("content", "")
        for m in msgs
    )
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_chat_rate_limit_returns_429(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client

    email = f"rpm-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    settings = get_settings()
    monkeypatch.setattr(settings, "onboarding_chat_rpm", 2)
    monkeypatch.setattr(settings, "onboarding_chat_rpm_window_seconds", 60)

    async def fake_turn(*args, **kwargs):
        return OnboardingTurn(reply="What project should we cover?", extracted_items=[])

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", fake_turn)

    app = create_app()
    mongo = get_mongo_client()[get_settings().mongo_db]
    app.state.mongo_db = mongo
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for i in range(2):
            ok = await client.post(
                "/api/v1/onboarding/chat",
                json={"message": f"hello {i}", "message_id": f"rpm-{i}"},
                cookies={"ic_access": token},
            )
            assert ok.status_code == 200
        limited = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "hello 2", "message_id": "rpm-2"},
            cookies={"ic_access": token},
        )
    assert limited.status_code == 429
    detail = limited.json()["detail"]
    assert detail["cause"] == "rate_limited"
    assert detail["retry_after_seconds"] >= 1
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_practise_intent_skips_llm_and_offers_start(
    monkeypatch, clean_users_table
):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client

    email = f"practise-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.flush()
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
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    async def should_not_run(*args, **kwargs):
        raise AssertionError("LLM should not run for practise intent")

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", should_not_run)

    app = create_app()
    mongo = get_mongo_client()[get_settings().mongo_db]
    app.state.mongo_db = mongo
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "I'd like to practise Python", "message_id": "p1"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "Python" in body["reply"]
    assert body["offer_start_interview"]["subject"] == "Python"
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_chat_message_id_is_idempotent(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client
    from app.services import conversation_store

    email = f"idem-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    calls = {"n": 0}

    async def fake_turn(*args, **kwargs):
        calls["n"] += 1
        return OnboardingTurn(reply=f"Hello #{calls['n']}", extracted_items=[])

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", fake_turn)

    app = create_app()
    mongo = get_mongo_client()[get_settings().mongo_db]
    app.state.mongo_db = mongo
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        a = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "Hi coach", "message_id": "same-id-1"},
            cookies={"ic_access": token},
        )
        b = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "Hi coach", "message_id": "same-id-1"},
            cookies={"ic_access": token},
        )
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["reply"] == b.json()["reply"]
    assert calls["n"] == 1
    msgs = await conversation_store.get_messages(mongo, user_id, limit=20)
    assert sum(1 for m in msgs if m.get("role") == "user") == 1
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
