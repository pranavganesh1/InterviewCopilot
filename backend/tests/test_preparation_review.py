import uuid

import httpx
import pytest

from app.agents.onboarding import ExtractedItem
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User
from app.models.vault import VaultItem
from app.services.candidate_intelligence import compose_candidate_intelligence
from app.services.preparation_review import (
    annotate_roadmap_completion,
    assessed_concepts_from_snapshot,
    build_profile_summary,
    build_review,
    build_roadmap,
    classify_item,
    improvement_topics_from_snapshot,
    intelligence_digest_from_snapshot,
    merge_review_patch,
    resolve_next_action,
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


def test_resolve_next_action_priority_order():
    open_session = {
        "session_id": "s1",
        "track_id": "t1",
        "track_subject": "Python",
        "question_index": 2,
        "max_turns": 15,
        "answered_count": 1,
    }
    assert (
        resolve_next_action(open_sessions=[open_session])["kind"] == "resume_session"
    )

    clarify = resolve_next_action(
        needs_clarification=[
            {
                "item_id": "p1",
                "category": "project",
                "title": "QCGNN",
                "status": "needs_clarification",
                "reason": "Still missing: technologies.",
            }
        ],
        roadmap=[{"id": "1", "subject": "Python", "track_type": "topic", "why": "focus"}],
    )
    assert clarify["kind"] == "clarify_profile"

    create_first = resolve_next_action(
        roadmap=[{"id": "1", "subject": "Python", "track_type": "topic", "why": "focus"}],
        existing_tracks=[],
    )
    assert create_first["kind"] == "create_track"
    assert create_first["subject"] == "Python"

    weak = resolve_next_action(
        existing_tracks=[{"id": "t2", "subject": "Algorithms"}],
        improvement_topics=["Recursion"],
        roadmap=[{"id": "1", "subject": "Java", "track_type": "topic", "why": "next"}],
    )
    assert weak["kind"] == "practise_weakness"
    assert weak["subject"] == "Recursion"

    recommend = resolve_next_action(
        existing_tracks=[{"id": "t3", "subject": "Python"}],
        roadmap=[
            {
                "id": "1",
                "subject": "Java",
                "track_type": "topic",
                "why": "next skill",
                "completion": "not_started",
            }
        ],
    )
    assert recommend["kind"] == "recommend_track"
    assert recommend["subject"] == "Java"


def test_roadmap_completion_from_persisted_state():
    steps = annotate_roadmap_completion(
        [{"id": "1", "subject": "Python", "title": "Python"}],
        existing_track_subjects={"python"},
        assessed_subjects={"python"},
    )
    assert steps[0]["completion"] == "completed"
    assert steps[0]["stage"] == 1


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
    # Without a snapshot, intelligence digest stays empty (backward compatible).
    assert review.get("intelligence") is None


def _snapshot_with_evidence():
    return compose_candidate_intelligence(
        user_profile={"skills": ["Go"], "education": "B.Tech"},
        vault_items=[
            {
                "id": "sk1",
                "category": "skill",
                "title": "Python",
                "details": {},
                "source": "resume",
                "missing_details": [],
            },
            {
                "id": "sk2",
                "category": "skill",
                "title": "Redis",
                "details": {},
                "source": "resume",
                "missing_details": [],
            },
            {
                "id": "p1",
                "category": "project",
                "title": "Campus Cart",
                "details": {"purpose": "Marketplace", "technologies": "FastAPI"},
                "source": "resume",
                "missing_details": ["architecture", "contribution", "outcome", "features"],
            },
        ],
        preferences={
            "interests": ["technical", "project", "skill"],
            "target_role": "Backend Developer",
            "focus_skills": ["Python"],
            "focus_projects": ["Campus Cart"],
            "confirmed": True,
        },
        profile_review=None,
        coach_context=None,
        tracks=[
            {
                "track_id": "t1",
                "subject": "Backend",
                "archived": False,
                "planned_topics": ["Python", "Redis", "Caching"],
            }
        ],
        turn_rows=[
            {
                "session_id": "s1",
                "track_id": "t1",
                "turn_index": 1,
                "question_area": "Python",
                "answer": "list comprehensions",
                "evaluation_coverage": "excellent",
                "evaluation_gaps": [],
                "evaluation_detail": {},
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "session_id": "s1",
                "track_id": "t1",
                "turn_index": 2,
                "question_area": "Python",
                "answer": "generators",
                "evaluation_coverage": "good",
                "evaluation_gaps": [],
                "evaluation_detail": {},
                "created_at": "2026-01-01T00:01:00+00:00",
            },
            {
                "session_id": "s1",
                "track_id": "t1",
                "turn_index": 3,
                "question_area": "SQL joins",
                "answer": "unsure",
                "evaluation_coverage": "none",
                "evaluation_gaps": ["outer joins"],
                "evaluation_detail": {},
                "created_at": "2026-01-01T00:02:00+00:00",
            },
        ],
        report_rows=[
            {
                "session_id": "s1",
                "track_id": "t1",
                "track_subject": "Backend",
                "track_archived": False,
                "created_at": "2026-01-02T00:00:00+00:00",
                "content": {
                    "summary_overview": "Mixed Python/SQL",
                    "strengths": ["Python fluency"],
                    "improvement_areas": ["SQL joins"],
                    "recommendations": ["Practise joins aloud"],
                    "competency_assessments": [],
                    "unassessed_topics": ["Caching"],
                },
            }
        ],
    )


def test_review_consumes_shared_snapshot_for_evidence():
    snap = _snapshot_with_evidence()
    items = [
        _item(category="skill", title="Python"),
        _item(category="skill", title="Redis"),
        _item(
            category="project",
            title="Campus Cart",
            details={"purpose": "Marketplace", "technologies": "FastAPI"},
        ),
        _item(category="education", title="B.Tech"),
    ]
    review = build_review(
        items,
        {
            "interests": ["technical", "project", "skill"],
            "target_role": "Backend Developer",
            "focus_skills": ["Python"],
            "focus_projects": ["Campus Cart"],
            "confirmed": True,
        },
        candidate_intelligence=snap,
    )
    intel = review["intelligence"]
    assert intel is not None
    assert intel["source"] == "candidate_intelligence_snapshot"
    assert intel["career_goals"]["target_role"] == "Backend Developer"
    assert "Python" in intel["demonstrated_strengths"] or any(
        "python" in s.lower() for s in intel["demonstrated_strengths"]
    )
    assert any("sql" in s.lower() or "join" in s.lower() for s in intel["areas_requiring_improvement"])
    # Redis claimed but not interview-answered → not listed as a weakness.
    assert not any("redis" in s.lower() for s in intel["areas_requiring_improvement"])
    assert "Redis" in intel["claimed_skills_without_interview"] or "Redis" in intel[
        "unverified_claims"
    ]
    assert intel["policy"]["unknown_is_not_weak"] is True
    # Vault project details come through (claims only).
    project = next(p for p in intel["projects"] if p["name"] == "Campus Cart")
    assert project["technologies"] == "FastAPI"
    assert project["evidence_kind"] == "claim"
    assert "architecture" in project["needs_clarification"]
    # Roadmap prioritizes interview improvement evidence.
    assert review["roadmap"][0]["subject"]
    assert "sql" in review["roadmap"][0]["subject"].lower() or "join" in review["roadmap"][0][
        "subject"
    ].lower()
    assert review["roadmap"][0].get("evidence_basis", {}).get("kind") == "interview_or_feedback"
    # Python skill can be confirmed from demonstrated interview evidence.
    python_status = next(s for s in review["item_statuses"] if s["title"] == "Python")
    assert python_status["status"] == "confirmed"
    redis_status = next(s for s in review["item_statuses"] if s["title"] == "Redis")
    assert redis_status["status"] == "not_assessed"


def test_snapshot_helpers_do_not_treat_claims_as_weak():
    snap = _snapshot_with_evidence()
    assessed = assessed_concepts_from_snapshot(snap)
    assert any("python" in a for a in assessed)
    assert any("sql" in a or "join" in a for a in assessed)
    improvements = improvement_topics_from_snapshot(snap)
    assert improvements
    assert not any("redis" == t.lower() for t in improvements)
    digest = intelligence_digest_from_snapshot(snap)
    assert digest["policy"]["claims_are_not_proof"] is True
    assert "Caching" in digest["not_assessed_from_briefs"] or "caching" in " ".join(
        digest["not_assessed_from_briefs"]
    ).lower()


def test_missing_snapshot_sections_do_not_break_review():
    review = build_review(
        [_item(category="skill", title="Java")],
        {"interests": ["skill"], "focus_skills": ["Java"], "confirmed": True},
        candidate_intelligence={"snapshot_version": 1},  # incomplete / partial
    )
    assert review["summary"]
    assert review["roadmap"]
    assert review["intelligence"] is not None
    assert review["intelligence"]["areas_requiring_improvement"] == []
    assert review["intelligence"]["demonstrated_strengths"] == []
    java = next(s for s in review["item_statuses"] if s["title"] == "Java")
    assert java["status"] == "not_assessed"


def test_build_roadmap_uses_snapshot_project_clarification():
    snap = _snapshot_with_evidence()
    roadmap = build_roadmap(
        {
            "interests": ["project"],
            "focus_projects": ["Campus Cart"],
            "confirmed": True,
        },
        [_item(category="project", title="Campus Cart", details={"purpose": "x"})],
        candidate_intelligence=snap,
    )
    project_step = next(s for s in roadmap if "Campus Cart" in s["subject"])
    assert "clarification" in project_step["why"].lower() or "missing" in " ".join(
        project_step.get("evidence_basis", {}).get("needs_clarification") or []
    ).lower() or project_step.get("evidence_basis", {}).get("needs_clarification")
    assert project_step["evidence_basis"]["kind"] == "vault_project_claim"


@pytest.mark.asyncio
async def test_complete_generates_persisted_review(monkeypatch, clean_users_table):
    from app.core.config import get_settings
    from app.db.mongo import get_mongo_db
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

    mongo = get_mongo_db()
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
        # Incomplete project details → clarify before creating a track.
        assert review["next_action"]["kind"] == "clarify_profile"
        assert any(i["status"] == "not_assessed" for i in review["item_statuses"])
        assert any(s.get("completion") for s in review["roadmap"])

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
