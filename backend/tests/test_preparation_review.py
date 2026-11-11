import uuid

import httpx
import pytest

from app.agents.onboarding import ExtractedItem
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User
from app.models.vault import VaultItem
from app.services.preparation_review import (
    build_profile_summary,
    build_review,
    build_roadmap,
    classify_item,
    merge_review_patch,
    _preserve_if_incomplete,
)
from app.services.vault_service import upsert_extracted_items


def _item(**kwargs):
    defaults = dict(
        user_id=uuid.uuid4(),
        category="skill",
        title="Python",
        details={},
        source="resume",
    )
    defaults.update(kwargs)
    item = VaultItem(**defaults)
    item.id = kwargs.get("id") or uuid.uuid4()
    return item


def test_skills_default_to_not_assessed_without_interview_evidence():
    skill = _item(category="skill", title="Python")
    result = classify_item(skill, duplicate_ids=set(), assessed_subjects=set())
    assert result["status"] == "not_assessed"
    assert "not yet evaluated" in result["reason"].lower() or "not yet" in result["reason"].lower()


def test_incomplete_project_needs_clarification():
    project = _item(category="project", title="QCGNN", details={"purpose": "research"})
    result = classify_item(project, duplicate_ids=set(), assessed_subjects=set())
    assert result["status"] == "needs_clarification"
    assert "missing" in result["reason"].lower()


def test_summary_uses_real_vault_facts_only():
    items = [
        _item(category="education", title="B.Tech CSE"),
        _item(category="skill", title="Java"),
        _item(category="project", title="Portfolio", details={}),
    ]
    summary = build_profile_summary(
        items,
        {
            "interests": ["skill", "technical"],
            "target_role": "Backend Intern",
            "focus_skills": ["Java"],
            "confirmed": True,
        },
    )
    assert "Here's what I understood about you" in summary
    assert "B.Tech CSE" in summary
    assert "Java" in summary
    assert "Portfolio" in summary
    assert "Backend Intern" in summary
    assert "proficiency score" not in summary.lower()


def test_roadmap_follows_selected_goals_not_hardcoded_examples():
    items = [
        _item(category="skill", title="Rust"),
        _item(category="project", title="Sensor Hub"),
    ]
    roadmap = build_roadmap(
        {
            "interests": ["skill", "project", "behavioral"],
            "focus_skills": ["Rust"],
            "focus_projects": ["Sensor Hub"],
            "confirmed": True,
        },
        items,
    )
    subjects = [s["subject"] for s in roadmap]
    assert "Rust" in subjects
    assert any("Sensor Hub" in s for s in subjects)
    assert "HR & Behavioral Interviews" in subjects
    # Example-only topics must not appear unless selected.
    assert "DSA" not in subjects
    assert "DBMS" not in subjects


def test_merge_preserves_user_summary_edit():
    review = build_review(
        [_item(category="education", title="B.Tech")],
        {"interests": ["technical"], "target_role": "SWE", "confirmed": True},
    )
    patched = merge_review_patch(review, {"summary": "Corrected: I study ECE, not CSE."})
    assert patched["summary_user_edit"] == "Corrected: I study ECE, not CSE."
    rebuilt = build_review(
        [_item(category="education", title="B.Tech")],
        {"interests": ["technical"], "target_role": "SWE", "confirmed": True},
        previous=patched,
    )
    assert rebuilt["summary"] == "Corrected: I study ECE, not CSE."


def test_skill_confirmed_only_with_interview_evidence():
    skill = _item(category="skill", title="Python")
    assessed = classify_item(
        skill, duplicate_ids=set(), assessed_subjects={"python fundamentals"}
    )
    assert assessed["status"] == "confirmed"


def test_roadmap_prioritizes_persisted_improvement_topics():
    roadmap = build_roadmap(
        {"interests": ["skill"], "focus_skills": ["Java"], "confirmed": True},
        [_item(category="skill", title="Java")],
        improvement_topics=["Recursion", "System design trade-offs"],
    )
    assert roadmap[0]["subject"] == "Recursion"
    assert "prior feedback" in roadmap[0]["practise"].lower() or "improvement" in roadmap[0]["why"].lower()
    assert any(s["subject"] == "Java" for s in roadmap)


def test_incomplete_rebuild_does_not_wipe_prior_review():
    previous = {
        "summary": "Solid prior summary about ECE and Rust.",
        "summary_user_edit": "Solid prior summary about ECE and Rust.",
        "roadmap": [
            {
                "id": "skill-rust",
                "title": "Rust practice",
                "why": "focus",
                "topics": ["Rust"],
                "practise": "practice",
                "track_type": "topic",
                "subject": "Rust",
                "action_label": "Start Rust",
            }
        ],
        "next_action": {"subject": "Rust", "action_label": "Start Recommended Interview"},
        "selected_next_track_id": "track-1",
        "item_statuses": [],
    }
    wiped = _preserve_if_incomplete(
        previous,
        {
            "summary": "",
            "roadmap": [],
            "next_action": None,
            "selected_next_track_id": None,
            "item_statuses": [],
        },
    )
    assert wiped["summary"].startswith("Solid prior summary")
    assert wiped["roadmap"][0]["subject"] == "Rust"
    assert wiped["selected_next_track_id"] == "track-1"


def test_next_action_and_roadmap_have_no_fake_scores():
    items = [
        _item(category="skill", title="Python"),
        _item(category="education", title="B.Tech"),
        _item(
            category="project",
            title="QCGNN",
            details={
                "purpose": "ML research",
                "technologies": "PyTorch",
                "architecture": "GNN",
                "contribution": "models",
                "outcome": "paper",
                "features": "quantum layer",
            },
        ),
    ]
    review = build_review(
        items,
        {
            "interests": ["skill", "technical"],
            "focus_skills": ["Python"],
            "target_role": "ML Intern",
            "technical_areas": ["Machine Learning"],
            "confirmed": True,
        },
    )
    assert review["next_action"] is not None
    assert "Python" in review["next_action"]["title"]
    assert review["next_action"]["action_label"] == "Start Recommended Interview"
    # Skills stay unassessed until a real interview report exists — no fake scores.
    skill_statuses = [s for s in review["item_statuses"] if s["category"] == "skill"]
    assert skill_statuses and all(s["status"] == "not_assessed" for s in skill_statuses)
    assert all("score" not in s for s in review["item_statuses"])
    assert all("score" not in step for step in review["roadmap"])
    assert "score" not in (review["next_action"] or {})


@pytest.mark.asyncio
async def test_complete_generates_persisted_review(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_client
    from app.services import conversation_store

    email = f"rev-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email, name="Kushal")
        session.add(user)
        await session.flush()
        await upsert_extracted_items(
            session,
            user.id,
            [
                ExtractedItem(category="project", title="QCGNN", details={"purpose": "ML"}),
                ExtractedItem(category="skill", title="Python", details={}),
                ExtractedItem(category="education", title="B.Tech", details={}),
            ],
            "resume",
        )
        await session.commit()
        token = create_access_token(str(user.id))
        user_id = str(user.id)

    mongo = get_mongo_client()[get_settings().mongo_db]
    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
    await conversation_store.set_preparation_preferences(
        mongo,
        user_id,
        {
            "interests": ["skill", "technical"],
            "target_role": "ML Intern",
            "focus_skills": ["Python"],
            "confirmed": True,
        },
    )

    async def fake_publish(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.events.publish_track_authoring_job", fake_publish, raising=False
    )

    app = create_app()
    app.state.mongo_db = mongo
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        complete = await client.post(
            "/api/v1/onboarding/complete", cookies={"ic_access": token}
        )
        assert complete.status_code == 200
        body = complete.json()
        assert body["onboarding_finished"] is True
        review = body["profile_review"]
        assert review and "QCGNN" in review["summary"]
        assert review["next_action"]["subject"]
        assert any(i["status"] == "not_assessed" for i in review["item_statuses"])

        # Refresh / login persistence via /auth/me and /onboarding/review
        me = await client.get("/api/v1/auth/me", cookies={"ic_access": token})
        assert me.status_code == 200
        assert me.json()["profile_review"]["summary"]

        again = await client.get("/api/v1/onboarding/review", cookies={"ic_access": token})
        assert again.status_code == 200
        assert again.json()["vault_fingerprint"] == review["vault_fingerprint"]

        patched = await client.patch(
            "/api/v1/onboarding/review",
            json={"summary": "I prefer focusing on systems work."},
            cookies={"ic_access": token},
        )
        assert patched.status_code == 200
        assert patched.json()["summary"] == "I prefer focusing on systems work."

        start = await client.post(
            "/api/v1/onboarding/review/start-recommended",
            json={},
            cookies={"ic_access": token},
        )
        assert start.status_code == 200
        assert start.json()["track"]["id"]
        assert start.json()["review"]["selected_next_track_id"] == start.json()["track"]["id"]

    await mongo.onboarding_conversations.delete_many({"user_id": user_id})
