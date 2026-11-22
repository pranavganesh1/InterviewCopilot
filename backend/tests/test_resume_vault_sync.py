"""Isolated tests: incremental resume sync, duplicates review, resume-data reset."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.onboarding import ExtractedItem
from app.main import create_app
from app.services.vault_service import (
    find_near_duplicates,
    normalize_title,
    reset_resume_sourced_items,
    resolve_duplicate_pair,
    sync_resume_items,
    titles_equivalent,
)


@pytest.fixture
async def user_row(clean_users_table):
    from app.db.sqlalchemy import SessionFactory
    from app.models.user import User

    async with SessionFactory() as db:
        user = User(
            google_sub=f"sub-{uuid.uuid4().hex}",
            email=f"sync-{uuid.uuid4().hex[:8]}@example.com",
            name="Sync Tester",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return SimpleNamespace(id=user.id, email=user.email)


@pytest.mark.asyncio
async def test_titles_equivalent_ignores_punctuation_and_filler():
    assert titles_equivalent(
        "IT Intern at Hindustan Aeronautics Limited (HAL)",
        "IT Intern - Hindustan Aeronautics Limited (HAL)",
    )
    assert titles_equivalent(
        "Cybersecurity Intern at Razz Security",
        "Cybersecurity Intern – Razz Security",
    )
    assert normalize_title("Backend / Architecture") == normalize_title("Backend/Architecture")


@pytest.mark.asyncio
async def test_sync_skips_equivalent_and_creates_only_new(user_row, clean_users_table):
    from app.db.sqlalchemy import SessionFactory
    from app.models.vault import VaultItem

    async with SessionFactory() as db:
        db.add(
            VaultItem(
                user_id=user_row.id,
                category="internship",
                title="IT Intern - Hindustan Aeronautics Limited (HAL)",
                details={"role": "intern"},
                source="resume",
            )
        )
        await db.commit()

        result = await sync_resume_items(
            db,
            user_row.id,
            [
                ExtractedItem(
                    category="internship",
                    title="IT Intern at Hindustan Aeronautics Limited (HAL)",
                    details={"role": "intern"},
                ),
                ExtractedItem(
                    category="project",
                    title="Music Database Management System",
                    details={"stack": "SQL"},
                ),
            ],
        )

    assert result["counts"]["created"] == 1
    assert result["counts"]["skipped"] == 1
    assert result["items_created"][0]["title"] == "Music Database Management System"
    assert result["items_skipped"][0]["reason"] == "equivalent_exists"


@pytest.mark.asyncio
async def test_sync_flags_enrichment_without_overwrite(user_row, clean_users_table):
    from app.db.sqlalchemy import SessionFactory
    from app.models.vault import VaultItem
    from app.services.vault_service import list_items

    async with SessionFactory() as db:
        db.add(
            VaultItem(
                user_id=user_row.id,
                category="project",
                title="Suraksha: Secure Aadhaar Verification System",
                details={"purpose": "secure verification"},
                source="resume",
            )
        )
        await db.commit()
        result = await sync_resume_items(
            db,
            user_row.id,
            [
                ExtractedItem(
                    category="project",
                    title="Suraksha Secure Aadhaar Verification System",
                    details={
                        "purpose": "secure verification",
                        "technologies": "FastAPI",
                    },
                )
            ],
        )
        items = await list_items(db, user_row.id)

    assert result["counts"]["created"] == 0
    assert result["counts"]["enrichment_candidates"] == 1
    assert items[0].details.get("technologies") is None  # not silently written


@pytest.mark.asyncio
async def test_sync_uncertain_similar_not_inserted(user_row, clean_users_table):
    from app.db.sqlalchemy import SessionFactory
    from app.models.vault import VaultItem
    from app.services.vault_service import list_items

    async with SessionFactory() as db:
        db.add(
            VaultItem(
                user_id=user_row.id,
                category="internship",
                title="Software Engineer Intern – Velcontech Solutions (Client: BAMUL), Bangalore, India",
                details={},
                source="resume",
            )
        )
        await db.commit()
        result = await sync_resume_items(
            db,
            user_row.id,
            [
                ExtractedItem(
                    category="internship",
                    title="Software Engineer Intern Velcontech Solutions BAMUL",
                    details={},
                )
            ],
        )
        items = await list_items(db, user_row.id)

    assert result["counts"]["created"] == 0
    assert result["counts"]["uncertain_matches"] >= 1 or result["counts"]["skipped"] >= 1
    assert len(items) == 1


@pytest.mark.asyncio
async def test_find_near_duplicates_and_resolve(user_row, clean_users_table):
    from app.db.sqlalchemy import SessionFactory
    from app.models.vault import VaultItem
    from app.services.vault_service import list_items

    async with SessionFactory() as db:
        a = VaultItem(
            user_id=user_row.id,
            category="education",
            title="PES University, Bangalore",
            details={"degree": "B.Tech"},
            source="resume",
        )
        b = VaultItem(
            user_id=user_row.id,
            category="education",
            title="PES University",
            details={},
            source="resume",
        )
        db.add_all([a, b])
        await db.commit()
        await db.refresh(a)
        await db.refresh(b)
        pairs = find_near_duplicates([a, b])
        assert pairs
        kept = await resolve_duplicate_pair(
            db, user_row.id, keep_id=a.id, discard_id=b.id, merge_details=True
        )
        items = await list_items(db, user_row.id)

    assert kept is not None
    assert len(items) == 1
    assert items[0].details.get("degree") == "B.Tech"


@pytest.mark.asyncio
async def test_reset_resume_sourced_preserves_manual(user_row, clean_users_table):
    from app.db.sqlalchemy import SessionFactory
    from app.models.vault import VaultItem
    from app.services.vault_service import list_items

    async with SessionFactory() as db:
        db.add_all(
            [
                VaultItem(
                    user_id=user_row.id,
                    category="skill",
                    title="Python",
                    details={},
                    source="resume",
                ),
                VaultItem(
                    user_id=user_row.id,
                    category="skill",
                    title="Custom Skill",
                    details={},
                    source="manual",
                ),
                VaultItem(
                    user_id=user_row.id,
                    category="project",
                    title="Chat Project",
                    details={},
                    source="onboarding_chat",
                ),
            ]
        )
        await db.commit()
        result = await reset_resume_sourced_items(db, user_row.id)
        items = await list_items(db, user_row.id)

    assert result["removed_count"] == 1
    assert {i.title for i in items} == {"Custom Skill", "Chat Project"}


@pytest.mark.asyncio
async def test_resume_reset_api_requires_confirmation(user_row, clean_users_table):
    from app.api import deps
    from app.core.security import create_access_token
    from app.db.sqlalchemy import SessionFactory
    from app.models.vault import VaultItem

    async with SessionFactory() as db:
        db.add(
            VaultItem(
                user_id=user_row.id,
                category="skill",
                title="Temp",
                details={},
                source="resume",
            )
        )
        await db.commit()

    token = create_access_token(str(user_row.id))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cookies = {"ic_access": token}
        denied = await client.post(
            "/api/v1/vault/resume-data/reset",
            json={"confirm": False},
            cookies=cookies,
        )
        assert denied.status_code == 422
        preview = await client.get(
            "/api/v1/vault/resume-data/reset-preview", cookies=cookies
        )
        assert preview.status_code == 200
        assert preview.json()["count"] == 1
        ok = await client.post(
            "/api/v1/vault/resume-data/reset",
            json={"confirm": True, "confirm_phrase": "RESET RESUME DATA"},
            cookies=cookies,
        )
        assert ok.status_code == 200
        assert ok.json()["removed_count"] == 1
    # silence unused import if deps not needed
    _ = deps
