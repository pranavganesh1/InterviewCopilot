"""Step 0: Shared Candidate Intelligence Composer — isolated unit tests.

No application database, no seed data, no network.
"""

from app.services import candidate_intelligence as ci


def _vault_skill(title: str, *, source: str = "resume", item_id: str = "v1") -> dict:
    return {
        "id": item_id,
        "category": "skill",
        "title": title,
        "details": {},
        "source": source,
        "missing_details": [],
    }


def _vault_project(
    title: str,
    *,
    details: dict | None = None,
    source: str = "resume",
    item_id: str = "p1",
) -> dict:
    return {
        "id": item_id,
        "category": "project",
        "title": title,
        "details": details or {},
        "source": source,
        "missing_details": [],
    }


def _turn(
    *,
    area: str,
    coverage: str,
    track_id: str = "t1",
    session_id: str = "s1",
    turn_index: int = 1,
    gaps: list[str] | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "track_id": track_id,
        "turn_index": turn_index,
        "question_area": area,
        "answer": f"answer about {area}",
        "evaluation_coverage": coverage,
        "evaluation_gaps": gaps or [],
        "evaluation_detail": {},
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _report(
    *,
    session_id: str = "s1",
    track_id: str = "t1",
    created_at: str = "2026-01-02T00:00:00+00:00",
    strengths: list[str] | None = None,
    improvements: list[str] | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "track_id": track_id,
        "track_subject": "Backend",
        "track_archived": False,
        "created_at": created_at,
        "content": {
            "summary_overview": "Solid fundamentals with gaps in SQL.",
            "strengths": strengths or ["Clear communication"],
            "improvement_areas": improvements or ["SQL joins"],
            "recommendations": ["Practise query plans aloud"],
            "competency_assessments": [
                {"competency_name": "Databases", "level": "developing", "status": "ASSESSED"}
            ],
            "unassessed_topics": ["Caching"],
        },
    }


def test_empty_history_produces_valid_snapshot():
    snap = ci.empty_candidate_intelligence_snapshot(reason="fresh candidate")
    assert snap["snapshot_version"] == 1
    assert snap["profile"]["career_goals"]["confirmed"] is False
    assert snap["projects"] == []
    assert snap["knowledge_evidence"]["interview_demonstrated"]["has_data"] is False
    assert snap["knowledge_evidence"]["not_assessed"]["evidence_kind"] == "not_assessed"
    assert snap["interview_history"]["tracks"] == []
    assert snap["feedback_history"]["reports"] == []
    assert (
        "fresh candidate" in " ".join(snap["composition_notes"]).lower()
        or snap["composition_notes"]
    )


def test_resume_claims_are_not_demonstrated():
    snap = ci.compose_candidate_intelligence(
        user_profile={"skills": ["Kubernetes"], "education": None},
        vault_items=[_vault_skill("Python"), _vault_skill("SQL")],
        preferences={"interests": ["technical"], "target_role": "Backend", "confirmed": True},
        profile_review=None,
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[],
    )
    claims = snap["knowledge_evidence"]["candidate_claims"]
    demo = snap["knowledge_evidence"]["interview_demonstrated"]
    assert claims["evidence_kind"] == "claim"
    assert {s["title"] for s in claims["skills"]} >= {"Python", "SQL"}
    assert demo["has_data"] is False
    assert demo["strengths"] == []
    assert demo["weaknesses"] == []
    # Claimed skills without interview appear under not_assessed, not weak.
    missing = snap["knowledge_evidence"]["not_assessed"]["claimed_skills_without_interview"]
    assert "Python" in missing
    assert "SQL" in missing


def test_missing_data_is_not_assessed_not_weak():
    snap = ci.compose_candidate_intelligence(
        user_profile=None,
        vault_items=[_vault_skill("Redis")],
        preferences={"interests": ["technical"], "confirmed": True},
        profile_review=None,
        coach_context=None,
        tracks=[
            {
                "track_id": "t1",
                "subject": "Backend",
                "archived": False,
                "planned_topics": ["Redis", "Networking"],
            }
        ],
        turn_rows=[],
        report_rows=[],
    )
    by_track = snap["knowledge_evidence"]["by_track"]
    assert len(by_track) == 1
    assert by_track[0]["demonstrated_weaknesses"] == []
    assert "Networking" in by_track[0]["not_assessed"] or "Redis" in by_track[0]["not_assessed"]
    assert by_track[0]["has_data"] is False


def test_track_specific_evidence_remains_scoped():
    snap = ci.compose_candidate_intelligence(
        user_profile=None,
        vault_items=[],
        preferences={"interests": ["technical"], "confirmed": True},
        profile_review=None,
        coach_context=None,
        tracks=[
            {
                "track_id": "t-sql",
                "subject": "SQL",
                "archived": False,
                "planned_topics": ["Joins", "Indexes"],
            },
            {
                "track_id": "t-os",
                "subject": "OS",
                "archived": False,
                "planned_topics": ["Processes", "Memory"],
            },
        ],
        turn_rows=[
            _turn(
                area="Joins",
                coverage="none",
                track_id="t-sql",
                session_id="s-sql",
                gaps=["outer joins"],
            ),
            # Two strong labels → mastered (single excellent alone is only "improving").
            _turn(
                area="Processes",
                coverage="excellent",
                track_id="t-os",
                session_id="s-os",
                turn_index=1,
            ),
            _turn(
                area="Processes",
                coverage="good",
                track_id="t-os",
                session_id="s-os",
                turn_index=2,
            ),
        ],
        report_rows=[],
        progression_by_track={
            "t-sql": {"strict_completed": 1, "guided_state": "LOCKED"},
            "t-os": {"strict_completed": 3, "guided_state": "UNLOCKED"},
        },
    )
    by_track = {row["track_id"]: row for row in snap["knowledge_evidence"]["by_track"]}
    assert by_track["t-sql"]["has_data"] is True
    assert by_track["t-os"]["has_data"] is True
    sql_weak = [c["concept"] for c in by_track["t-sql"]["demonstrated_weaknesses"]]
    os_strong = [c["concept"] for c in by_track["t-os"]["demonstrated_strengths"]]
    assert any("join" in c for c in sql_weak)
    assert any("process" in c for c in os_strong)
    # SQL weakness must not appear as OS-track demonstrated weakness.
    os_weak = [c["concept"] for c in by_track["t-os"]["demonstrated_weaknesses"]]
    assert not any("join" in c for c in os_weak)

    hist = {row["track_id"]: row for row in snap["interview_history"]["tracks"]}
    assert hist["t-sql"]["progression"]["guided_state"] == "LOCKED"
    assert hist["t-os"]["progression"]["guided_state"] == "UNLOCKED"
    assert snap["interview_history"]["cross_track_overview"]["scope"] == "cross_track_digest"


def test_duplicate_feedback_session_not_counted_twice():
    snap = ci.compose_candidate_intelligence(
        user_profile=None,
        vault_items=[],
        preferences=None,
        profile_review=None,
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[
            _report(session_id="s1", created_at="2026-01-01T00:00:00+00:00", improvements=["A"]),
            _report(session_id="s1", created_at="2026-02-01T00:00:00+00:00", improvements=["B"]),
            _report(session_id="s2", created_at="2026-03-01T00:00:00+00:00", improvements=["C"]),
        ],
    )
    reports = snap["feedback_history"]["reports"]
    session_ids = [r["session_id"] for r in reports]
    assert session_ids.count("s1") == 1
    assert "s2" in session_ids
    # Newest s1 kept.
    s1 = next(r for r in reports if r["session_id"] == "s1")
    assert s1["improvement_areas"] == ["B"]
    assert s1["freshness"]["created_at"] == "2026-02-01T00:00:00+00:00"


def test_user_profile_vs_vault_conflict_retained_both():
    snap = ci.compose_candidate_intelligence(
        user_profile={
            "skills": ["Java", "Kotlin"],
            "education": "B.Tech CSE",
            "professional_title": "Student",
        },
        vault_items=[
            _vault_skill("Python", item_id="1"),
            _vault_skill("Java", item_id="2"),
            {
                "id": "e1",
                "category": "education",
                "title": "M.S. Data Science",
                "details": {},
                "source": "resume",
                "missing_details": [],
            },
        ],
        preferences={"interests": ["technical"], "confirmed": False},
        profile_review=None,
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[],
    )
    conflicts = snap["profile"]["source_conflicts"]
    assert conflicts
    skills_conflict = next(c for c in conflicts if c["field"] == "skills")
    assert skills_conflict["resolution"] == "retain_both"
    assert "Kotlin" in skills_conflict["user_profile_only"]
    assert "Python" in skills_conflict["vault_only"]
    edu_conflict = next(c for c in conflicts if c["field"] == "education")
    assert edu_conflict["resolution"] == "retain_both"
    # Neither source wiped.
    assert snap["profile"]["user_profile"]["skills"] == ["Java", "Kotlin"]
    vault_skill_titles = {s["title"] for s in snap["profile"]["vault"]["skills"]}
    assert vault_skill_titles >= {"Python", "Java"}


def test_partial_snapshot_when_sources_marked_unavailable():
    snap = ci.compose_candidate_intelligence(
        user_profile=None,
        vault_items=[_vault_project("Campus Cart", details={"technologies": "FastAPI"})],
        preferences={
            "interests": ["project"],
            "focus_projects": ["Campus Cart"],
            "confirmed": True,
        },
        profile_review=None,
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[],
        sources_available={
            "vault": True,
            "onboarding": False,
            "turns": False,
            "feedback": False,
            "user_profile": False,
        },
        composition_notes=["turns unavailable: OperationalError", "feedback unavailable: Timeout"],
    )
    assert snap["sources_available"]["vault"] is True
    assert snap["sources_available"]["turns"] is False
    assert snap["projects"][0]["name"] == "Campus Cart"
    assert snap["projects"][0]["technologies"] == "FastAPI"
    assert snap["projects"][0]["evidence_kind"] == "claim"
    assert "architecture" in snap["projects"][0]["needs_clarification"]
    assert snap["knowledge_evidence"]["interview_demonstrated"]["has_data"] is False


def test_preferences_distinct_from_demonstrated_ability():
    snap = ci.compose_candidate_intelligence(
        user_profile=None,
        vault_items=[],
        preferences={
            "interests": ["behavioral", "technical"],
            "behavioral_goals": "conflict resolution",
            "target_role": "SDE Intern",
            "confirmed": True,
        },
        profile_review={"next_action": {"kind": "start_track", "title": "Start Backend"}},
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[],
    )
    prep = snap["preparation_preferences"]
    assert prep["evidence_kind"] == "preference"
    assert prep["behavioral_interview_preference"] is True
    assert prep["goals"]["behavioral_goals"] == "conflict resolution"
    assert prep["preferred_mode"] is None
    assert "per session" in prep["session_options_note"].lower()
    assert prep["profile_review_next_action"]["kind"] == "start_track"
    assert snap["knowledge_evidence"]["interview_demonstrated"]["has_data"] is False


def test_project_details_never_invented():
    snap = ci.compose_candidate_intelligence(
        user_profile=None,
        vault_items=[
            _vault_project(
                "Sparse Notes",
                details={"purpose": "Note taking app"},
            )
        ],
        preferences=None,
        profile_review=None,
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[],
    )
    project = snap["projects"][0]
    assert project["description"] == "Note taking app"
    assert project["contribution"] is None
    assert project["architecture"] is None
    assert "contribution" in project["needs_clarification"]
    assert "architecture" in project["needs_clarification"]


def test_multi_source_composition_separates_claims_and_demo():
    snap = ci.compose_candidate_intelligence(
        user_profile={"skills": ["Go"], "education": "B.S."},
        vault_items=[
            _vault_skill("Go"),
            _vault_skill("PostgreSQL"),
            _vault_project(
                "Campus Cart",
                details={
                    "purpose": "Campus marketplace",
                    "technologies": "FastAPI, Postgres",
                    "contribution": "API owner",
                    "architecture": "REST + Postgres",
                    "outcome": "50 users",
                },
            ),
        ],
        preferences={
            "interests": ["technical", "project"],
            "target_role": "Backend Developer",
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
                "planned_topics": ["PostgreSQL", "REST", "Caching"],
            }
        ],
        turn_rows=[
            _turn(area="PostgreSQL", coverage="good", track_id="t1", session_id="s1"),
            _turn(
                area="REST",
                coverage="none",
                track_id="t1",
                session_id="s1",
                turn_index=2,
            ),
        ],
        report_rows=[_report(session_id="s1", track_id="t1")],
    )
    assert snap["profile"]["career_goals"]["target_role"] == "Backend Developer"
    assert snap["projects"][0]["contribution"] == "API owner"
    demo = snap["knowledge_evidence"]["interview_demonstrated"]
    assert demo["has_data"] is True
    # PostgreSQL demonstrated does not promote vault-only Caching to weakness.
    by_track = snap["knowledge_evidence"]["by_track"][0]
    assert "Caching" in by_track["not_assessed"]
    assert snap["feedback_history"]["reports"][0]["summary_overview"]
    assert snap["provenance_policy"]["claims_are_not_proof"] is True
