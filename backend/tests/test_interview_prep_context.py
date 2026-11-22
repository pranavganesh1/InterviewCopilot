"""Step 3: interview prep context from shared candidate intelligence (isolated)."""

from types import SimpleNamespace

from app.services.candidate_intelligence import (
    build_interview_prep_context,
    compact_brief_authoring_context,
    compose_candidate_intelligence,
    filter_vault_items_for_selected_projects,
    resolve_selected_project_titles,
)
from app.services import probe as probe_service


def _snap(*, focus_projects=None, turns=True):
    turn_rows = []
    if turns:
        turn_rows = [
            {
                "session_id": "s1",
                "track_id": "t-backend",
                "turn_index": 1,
                "question_area": "Python",
                "answer": "ok",
                "evaluation_coverage": "excellent",
                "evaluation_gaps": [],
                "evaluation_detail": {},
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "session_id": "s1",
                "track_id": "t-backend",
                "turn_index": 2,
                "question_area": "Python",
                "answer": "ok2",
                "evaluation_coverage": "good",
                "evaluation_gaps": [],
                "evaluation_detail": {},
                "created_at": "2026-01-01T00:01:00+00:00",
            },
            {
                "session_id": "s1",
                "track_id": "t-backend",
                "turn_index": 3,
                "question_area": "SQL joins",
                "answer": "weak",
                "evaluation_coverage": "none",
                "evaluation_gaps": ["outer joins"],
                "evaluation_detail": {},
                "created_at": "2026-01-01T00:02:00+00:00",
            },
            {
                "session_id": "s2",
                "track_id": "t-ml",
                "turn_index": 1,
                "question_area": "Gradient descent",
                "answer": "weak",
                "evaluation_coverage": "none",
                "evaluation_gaps": [],
                "evaluation_detail": {},
                "created_at": "2026-02-01T00:00:00+00:00",
            },
        ]
    return compose_candidate_intelligence(
        user_profile={"skills": ["Go"], "education": "B.Tech"},
        vault_items=[
            {
                "id": "1",
                "category": "skill",
                "title": "Python",
                "details": {},
                "source": "resume",
                "missing_details": [],
            },
            {
                "id": "2",
                "category": "project",
                "title": "QCGNN",
                "details": {"purpose": "ML research", "technologies": "PyTorch"},
                "source": "resume",
                "missing_details": [],
            },
            {
                "id": "3",
                "category": "project",
                "title": "MERN Stack Application",
                "details": {"purpose": "web app", "technologies": "React"},
                "source": "resume",
                "missing_details": [],
            },
            {
                "id": "4",
                "category": "project",
                "title": "Music Database Management System",
                "details": {"purpose": "DBMS", "technologies": "SQL"},
                "source": "resume",
                "missing_details": [],
            },
            {
                "id": "5",
                "category": "internship",
                "title": "SRE Intern",
                "details": {},
                "source": "resume",
                "missing_details": [],
            },
        ],
        preferences={
            "interests": ["technical", "project"],
            "target_role": "Backend Developer",
            "focus_projects": focus_projects or [],
            "confirmed": True,
        },
        profile_review=None,
        coach_context=None,
        tracks=[
            {
                "track_id": "t-backend",
                "subject": "Backend",
                "archived": False,
                "planned_topics": ["Python", "SQL", "Caching"],
            },
            {
                "track_id": "t-ml",
                "subject": "ML",
                "archived": False,
                "planned_topics": ["Gradient descent"],
            },
        ],
        turn_rows=turn_rows,
        report_rows=[],
    )


def test_no_arbitrary_primary_project_when_unselected():
    snap = _snap(focus_projects=[])
    selected = resolve_selected_project_titles(snap)
    assert selected == []
    prep = build_interview_prep_context(snap, track_id="t-backend", track_subject="Backend")
    assert prep["selected_projects"] == []
    assert "No project explicitly selected" in prep["project_selection_note"]
    assert prep["policy"]["no_arbitrary_primary_project"] is True


def test_selected_project_respected_not_mern_default():
    snap = _snap(focus_projects=["QCGNN"])
    prep = build_interview_prep_context(snap, track_id="t-backend")
    assert prep["selected_projects"] == ["QCGNN"]
    assert "MERN Stack Application" not in prep["selected_projects"]
    assert prep["selected_project_details"][0]["name"] == "QCGNN"
    assert prep["selected_project_details"][0]["evidence_kind"] == "claim"


def test_claim_seeds_can_select_project():
    snap = _snap(focus_projects=[])
    selected = resolve_selected_project_titles(
        snap, claim_seeds=[{"title": "Music Database Management System", "claim": "owned schema"}]
    )
    assert selected == ["Music Database Management System"]


def test_track_scoped_weaknesses_not_cross_imported():
    snap = _snap(focus_projects=["QCGNN"])
    backend = build_interview_prep_context(snap, track_id="t-backend", track_subject="Backend")
    ml = build_interview_prep_context(snap, track_id="t-ml", track_subject="ML")
    assert backend["evidence_scope"] == "track"
    assert ml["evidence_scope"] == "track"
    assert any("sql" in w.lower() or "join" in w.lower() for w in backend["demonstrated_weaknesses"])
    assert not any("gradient" in w.lower() for w in backend["demonstrated_weaknesses"])
    assert any("gradient" in w.lower() for w in ml["demonstrated_weaknesses"])


def test_filter_vault_items_keeps_skills_strips_unselected_projects():
    items = [
        SimpleNamespace(category="project", title="QCGNN"),
        SimpleNamespace(category="project", title="MERN Stack Application"),
        SimpleNamespace(category="skill", title="Python"),
        SimpleNamespace(category="internship", title="SRE Intern"),
    ]
    filtered = filter_vault_items_for_selected_projects(items, ["QCGNN"])
    titles = [i.title for i in filtered]
    assert "QCGNN" in titles
    assert "Python" in titles
    assert "SRE Intern" in titles
    assert "MERN Stack Application" not in titles

    none_selected = filter_vault_items_for_selected_projects(items, [])
    assert [i.title for i in none_selected] == ["Python", "SRE Intern"]


def test_first_interview_without_history_still_builds_context():
    snap = _snap(focus_projects=[], turns=False)
    prep = build_interview_prep_context(snap, track_id="t-backend", mode="strict", duration_minutes=45)
    assert prep["demonstrated_strengths"] == []
    assert prep["demonstrated_weaknesses"] == []
    assert prep["session_preferences"]["mode"] == "strict"
    assert prep["session_preferences"]["duration_minutes"] == 45
    compact = compact_brief_authoring_context(prep)
    assert compact["policy"]["claims_are_not_proof"] is True
    assert compact["selected_projects"] == []


def test_attach_session_opts_persists_candidate_context():
    snap = _snap(focus_projects=["QCGNN"])
    prep = build_interview_prep_context(snap, track_id="t-backend")
    plan = [{"topic": "Python", "objective": "x", "difficulty": "foundational", "format": "conceptual"}]
    out = probe_service.attach_session_opts(
        plan,
        use_resume=True,
        focus_weak=False,
        defense_mode=False,
        candidate_context=prep,
        selected_projects=prep["selected_projects"],
    )
    opts = probe_service.session_opts_from_plan(out)
    assert opts["selected_projects"] == ["QCGNN"]
    assert opts["candidate_context"]["selected_projects"] == ["QCGNN"]
    assert opts["candidate_context"]["policy"]["no_arbitrary_primary_project"] is True
    assert "demonstrated_weaknesses" in opts["candidate_context"]


def test_claims_remain_separate_from_demonstrated():
    snap = _snap(focus_projects=["QCGNN"])
    prep = build_interview_prep_context(snap, track_id="t-backend")
    assert prep["background"]["evidence_kind"] == "claim"
    assert "Python" in prep["background"]["skills"]
    # Demonstrated list comes from turns, not from merely listing the skill in vault.
    assert all(isinstance(x, str) for x in prep["demonstrated_strengths"])
    assert prep["policy"]["claims_are_not_proof"] is True
