"""Diverse backgrounds + flexible vault readiness for onboarding."""

import uuid

import httpx
import pytest

from app.agents.onboarding import compute_profile_gaps, derive_phase, vault_is_ready
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.mongo import get_mongo_client
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User
from app.models.vault import VaultItem
from app.services.conversation_store import merge_coach_context, set_preparation_preferences
from app.services.preparation_goals import (
    build_resume_goal_options,
    infer_candidate_background,
    suggest_roles,
    suggest_technical_areas,
)
from app.services.vault_service import RESUME_WELCOME_MARKER, build_profile_review_message


def _summary(*rows: tuple[str, str]) -> list[dict]:
    return [{"category": c, "title": t, "details": {}} for c, t in rows]


def test_infer_commerce_physics_cs_backgrounds():
    commerce = infer_candidate_background(
        _summary(("education", "B.Com Accounting"), ("skill", "Excel"))
    )
    assert commerce["field_family"] == "commerce"
    assert any("Business" in t or "Excel" in t for t in commerce["suggested_prep_topics"])

    physics = infer_candidate_background(
        _summary(("education", "B.Sc Physics"), ("project", "Optics Lab Study"))
    )
    assert physics["field_family"] == "physics"

    cs = infer_candidate_background(
        _summary(
            ("education", "B.Tech Computer Science"),
            ("skill", "Python"),
            ("project", "QCGNN"),
        )
    )
    assert cs["field_family"] == "computer_science"


def test_roles_not_forced_to_software_for_commerce():
    roles = suggest_roles(_summary(("education", "B.Com"), ("skill", "Excel")))
    assert "Business Analyst" in roles or "Financial Analyst" in roles
    assert roles[0] != "Software Engineer Intern"
    assert "I'm still exploring" in roles


def test_welcome_personalized_by_field():
    uid = uuid.uuid4()
    commerce_items = [
        VaultItem(
            user_id=uid,
            category="education",
            title="B.Com Finance",
            details={},
            source="resume",
        ),
        VaultItem(
            user_id=uid, category="skill", title="Excel", details={}, source="resume"
        ),
    ]
    msg = build_profile_review_message(commerce_items)
    assert RESUME_WELCOME_MARKER in msg
    assert "Commerce" in msg or "B.Com" in msg or "Finance" in msg
    assert "11 more" not in msg

    physics_items = [
        VaultItem(
            user_id=uid,
            category="education",
            title="B.Sc Physics",
            details={},
            source="resume",
        ),
    ]
    pmsg = build_profile_review_message(physics_items)
    assert "Physics" in pmsg or "analytical" in pmsg.lower()


def test_incomplete_no_projects_no_experience_self_taught():
    no_edu = infer_candidate_background(_summary(("skill", "SQL"), ("skill", "Excel")))
    assert no_edu["has_education"] is False
    assert no_edu["has_projects"] is False
    assert no_edu["experience_signal"] == "skills_projects"

    areas = suggest_technical_areas(_summary(("skill", "SQL"), ("skill", "Excel")))
    assert "SQL" in areas or "Excel" in areas

    empty = infer_candidate_background([])
    assert empty["field_family"] == "general"
    assert empty["experience_signal"] == "none"
    assert empty["has_internships"] is False

    # Self-taught / no degree — skills alone still unlock prep options.
    opts = build_resume_goal_options(_summary(("skill", "Python"), ("skill", "Excel")))
    assert opts["suggested_skills"]
    assert "I'm still exploring" in opts["suggested_roles"]


def test_discontinued_education_and_undecided_goals():
    # Education title that mentions discontinued — still optional, no negative label.
    bg = infer_candidate_background(
        _summary(("education", "B.Com (discontinued)"), ("skill", "Tally"))
    )
    assert bg["field_family"] == "commerce"
    assert bg["has_education"] is True

    roles = suggest_roles(_summary(("skill", "Communication")))
    assert "I'm still exploring" in roles

    empty_welcome = build_profile_review_message([])
    assert "No degree or project required" in empty_welcome or "interested" in empty_welcome.lower()


def test_vault_ready_with_partial_or_skipped_profile():
    empty = []
    assert vault_is_ready(empty) is False
    assert vault_is_ready(empty, {"proceed_to_goals": True}) is True
    assert vault_is_ready(_summary(("skill", "Excel"))) is True

    gaps = compute_profile_gaps(_summary(("skill", "Excel")))
    assert gaps["optional"] is True
    assert "education" in gaps["missing_categories"]
    assert gaps["category_status"]["skill"] == "present"
    assert gaps["category_status"]["education"] == "not_provided"

    skipped = compute_profile_gaps(
        _summary(("skill", "Excel")),
        coach_context={"skipped_categories": ["education", "project"]},
    )
    assert skipped["missing_categories"] == []
    assert skipped["category_status"]["education"] == "skipped"

    na = compute_profile_gaps(
        [],
        coach_context={"not_applicable_categories": ["project", "education"]},
    )
    assert na["category_status"]["project"] == "not_applicable"


def test_phase_allows_goals_without_full_cs_vault():
    prefs = {"interests": [], "confirmed": False}
    phase = derive_phase(
        vault_summary=_summary(("education", "B.Sc Physics")),
        preferences=prefs,
        already_finished=False,
    )
    assert phase == "goals"

    proceed = derive_phase(
        vault_summary=[],
        preferences=prefs,
        already_finished=False,
        coach_context={"proceed_to_goals": True},
    )
    assert proceed == "goals"


@pytest.mark.asyncio
async def test_complete_with_skill_only_vault(clean_users_table):
    """Start Preparing only needs interests — education/projects optional."""
    email = f"flex-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email, name="Flex")
        session.add(user)
        await session.flush()
        session.add(
            VaultItem(
                user_id=user.id,
                category="skill",
                title="Excel",
                details={},
                source="manual",
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    app = create_app()
    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})

    await set_preparation_preferences(
        app.state.mongo_db,
        user_id,
        {"interests": ["behavioral"], "confirmed": False},
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        done = await client.post(
            "/api/v1/onboarding/complete",
            cookies={"ic_access": token},
        )
        assert done.status_code == 200, done.text
        assert done.json()["onboarding_finished"] is True

    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_coach_context_persists_across_state(clean_users_table):
    email = f"ctx-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email, name="Ctx")
        session.add(user)
        await session.flush()
        session.add(
            VaultItem(
                user_id=user.id,
                category="education",
                title="B.Com",
                details={},
                source="resume",
            )
        )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    app = create_app()
    app.state.mongo_db = get_mongo_client()[get_settings().mongo_db]
    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})

    await merge_coach_context(
        app.state.mongo_db,
        user_id,
        {
            "asked_questions": ["What role interests you?"],
            "confirmed_facts": ["Studied B.Com"],
            "current_topic": "career_goals",
            "skipped_categories": ["project"],
            "background": {"field_family": "commerce"},
        },
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        state = await client.get(
            "/api/v1/onboarding/state",
            cookies={"ic_access": token},
        )
        assert state.status_code == 200, state.text
        body = state.json()
        ctx = body.get("coach_context") or {}
        assert "What role interests you?" in (ctx.get("asked_questions") or [])
        assert "Studied B.Com" in (ctx.get("confirmed_facts") or [])
        assert ctx.get("current_topic") == "career_goals"
        assert "project" in (ctx.get("skipped_categories") or [])
        assert body.get("optional_categories") is True

    await app.state.mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
