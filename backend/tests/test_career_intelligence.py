"""Phase D Feature 3: Career Readiness Intelligence (offline / mocked)."""

from types import SimpleNamespace

from app.services import career_intelligence as ci
from app.services import weakness as weakness_service


def _concept(name, status, times=2, last="partial", trend=None, gaps=None):
    return {
        "concept": name,
        "status": status,
        "times_asked": times,
        "last_coverage": last,
        "trend": trend or [last],
        "missing_concepts": gaps or [],
        "evidence": [{"session_id": "s1", "turn_index": 1, "coverage": last}],
    }


def test_no_completed_interviews_insufficient_evidence():
    out = ci.compose_career_intelligence(
        concept_summary={"concepts": [], "history": [], "has_data": False},
        assessment_rows=[],
        planned_topics=["SQL", "OS"],
        project_defense_aggregate=None,
        prefs={"target_role": "Backend Intern"},
        domain_profile={"category": "programming", "uses_code": True},
    )
    assert out["career_readiness"]["level"] == "insufficient_evidence"
    assert out["career_readiness"]["evidence_index"] is None
    assert out["not_yet_assessed"]
    assert out["progress"]["available"] is False
    assert any(a["kind"] == "start_interview" for a in out["next_actions"])


def test_one_completed_interview_no_overtime_progress():
    summary = weakness_service.aggregate_turns(
        [
            SimpleNamespace(
                question_area="SQL",
                answer="joins",
                evaluation_coverage="partial",
                evaluation_gaps=["outer joins"],
                session_id="s1",
                turn_index=1,
                evaluation_detail={},
            )
        ],
        session_order=["s1"],
    )
    out = ci.compose_career_intelligence(
        concept_summary=summary,
        assessment_rows=[
            {
                "session_id": "s1",
                "track_subject": "SQL",
                "overall_score": 50,
                "questions_attempted": 1,
                "created_at": "2026-01-01",
            }
        ],
        planned_topics=["SQL", "Indexes"],
        project_defense_aggregate=None,
        prefs={"target_role": "Data Analyst"},
        domain_profile={"category": "programming"},
    )
    assert out["progress"]["available"] is False
    assert "two interviews" in out["progress"]["reason"].lower() or "at least two" in out[
        "progress"
    ]["reason"].lower()
    assert out["career_readiness"]["level"] in ("early", "developing", "building", "needs_focused_practice")


def test_multiple_interviews_improving_and_persistent():
    summary = {
        "has_data": True,
        "history": [{"session_id": "s1", "areas": {"sql": 50}}],
        "concepts": [
            _concept("sql joins", "improving", times=3, last="good", trend=["none", "partial", "good"]),
            _concept("hashmaps", "weak", times=3, last="none", trend=["none", "partial", "none"], gaps=["collisions"]),
            _concept("recursion", "mastered", times=2, last="excellent", trend=["good", "excellent"]),
            _concept("graphs", "weak", times=1, last="partial"),  # not persistent (times < 2 for persistent filter uses >=2)
        ],
    }
    out = ci.compose_career_intelligence(
        concept_summary=summary,
        assessment_rows=[
            {"session_id": "s1", "overall_score": 40, "questions_attempted": 4, "created_at": "2026-01-01"},
            {"session_id": "s2", "overall_score": 70, "questions_attempted": 5, "created_at": "2026-02-01"},
        ],
        planned_topics=["SQL", "Networking"],
        project_defense_aggregate=None,
        prefs={"target_role": "Backend Intern", "interests": ["technical"]},
        domain_profile={"category": "programming", "uses_code": True},
        focus_track_id="t1",
    )
    assert out["progress"]["available"] is True
    assert "sql joins" in out["progress"]["improving"]
    assert "hashmaps" in out["progress"]["persistent_weaknesses"]
    assert "recursion" in [s["concept"] for s in out["strengths"]]
    assert any(r["topic"] == "hashmaps" for r in out["recommendations"])
    assert out["roadmap"]
    assert out["integrations"]["adaptive_knowledge"] is True


def test_unanswered_excluded_via_aggregate_turns():
    turns = [
        SimpleNamespace(
            question_area="Trees",
            answer=None,
            evaluation_coverage="none",
            evaluation_gaps=[],
            session_id="s1",
            turn_index=1,
            evaluation_detail={},
        ),
        SimpleNamespace(
            question_area="Trees",
            answer="BST ordered",
            evaluation_coverage="good",
            evaluation_gaps=[],
            session_id="s1",
            turn_index=2,
            evaluation_detail={},
        ),
    ]
    summary = weakness_service.aggregate_turns(turns, session_order=["s1"])
    # Only answered turn counts.
    trees = next(c for c in summary["concepts"] if c["concept"] == "trees")
    assert trees["times_asked"] == 1


def test_not_yet_assessed_not_treated_as_failure():
    out = ci.compose_career_intelligence(
        concept_summary={
            "has_data": True,
            "concepts": [_concept("sql", "mastered", last="excellent", trend=["excellent", "excellent"])],
            "history": [],
        },
        assessment_rows=[
            {"session_id": "s1", "overall_score": 90, "questions_attempted": 5, "created_at": "a"},
            {"session_id": "s2", "overall_score": 88, "questions_attempted": 5, "created_at": "b"},
        ],
        planned_topics=["SQL", "Operating Systems", "Networks"],
        project_defense_aggregate=None,
        prefs={"target_role": "SDE Intern"},
        domain_profile={"category": "programming"},
    )
    assert "Operating Systems" in out["not_yet_assessed"] or "operating systems" in [
        x.lower() for x in out["not_yet_assessed"]
    ]
    assert all(s["concept"] != "Operating Systems" for s in out["improvement_areas"])


def test_project_defense_integration_in_recommendations():
    out = ci.compose_career_intelligence(
        concept_summary={"concepts": [], "history": [], "has_data": False},
        assessment_rows=[
            {"session_id": "s1", "overall_score": 60, "questions_attempted": 6, "created_at": "a"},
            {"session_id": "s2", "overall_score": 65, "questions_attempted": 6, "created_at": "b"},
        ],
        planned_topics=[],
        project_defense_aggregate={
            "has_data": True,
            "projects_assessed": ["Campus nav"],
            "demonstrated": ["Campus nav: architecture"],
            "knowledge_gaps": ["missing trade-off reasoning"],
            "ownership_unclear": ["Campus nav"],
        },
        prefs={"target_role": "Full Stack Intern"},
        domain_profile={"category": "programming"},
        has_projects=True,
        focus_track_id="t1",
    )
    assert out["integrations"]["project_defense"] is True
    assert out["project_defense"]["has_data"]
    topics = [r["topic"].lower() for r in out["recommendations"]]
    assert any("trade-off" in t or "ownership" in t for t in topics)
    assert any(a["kind"] == "defend_projects" for a in out["next_actions"])


def test_commerce_discipline_practice_wording():
    out = ci.compose_career_intelligence(
        concept_summary={
            "has_data": True,
            "concepts": [
                _concept("ratio analysis", "weak", times=2, last="none", gaps=["current ratio"])
            ],
            "history": [],
        },
        assessment_rows=[
            {"session_id": "s1", "overall_score": 40, "questions_attempted": 4, "created_at": "a"},
            {"session_id": "s2", "overall_score": 45, "questions_attempted": 4, "created_at": "b"},
        ],
        planned_topics=["Accounting"],
        project_defense_aggregate=None,
        prefs={"interests": ["commerce", "finance"], "target_role": "Finance Analyst"},
        domain_profile={"category": "business", "uses_code": False},
    )
    assert out["career_readiness"]["discipline"] == "business"
    assert any("numeric" in r["practice"].lower() or "case" in r["practice"].lower() for r in out["recommendations"])


def test_physics_discipline_and_target_role():
    out = ci.compose_career_intelligence(
        concept_summary={
            "has_data": True,
            "concepts": [_concept("newton laws", "weak", times=2, last="partial")],
            "history": [],
        },
        assessment_rows=[
            {"session_id": "s1", "overall_score": 50, "questions_attempted": 5, "created_at": "a"},
            {"session_id": "s2", "overall_score": 55, "questions_attempted": 5, "created_at": "b"},
        ],
        planned_topics=["Electromagnetism"],
        project_defense_aggregate=None,
        prefs={"interests": ["physics"], "target_role": "Research Intern"},
        domain_profile={"category": "science", "uses_code": False},
    )
    assert out["career_readiness"]["discipline"] == "science"
    assert out["career_readiness"]["target_role"] == "Research Intern"
    assert any("assumptions" in r["practice"].lower() or "paper" in r["practice"].lower() for r in out["recommendations"])


def test_evidence_index_only_with_enough_data():
    concepts = [
        _concept(f"c{i}", "mastered", times=2, last="excellent", trend=["good", "excellent"])
        for i in range(8)
    ]
    summary = {"has_data": True, "concepts": concepts, "history": []}
    thin = ci.compose_career_intelligence(
        concept_summary={"has_data": True, "concepts": concepts[:2], "history": []},
        assessment_rows=[{"session_id": "s1", "overall_score": 80, "questions_attempted": 2}],
        planned_topics=[],
        project_defense_aggregate=None,
        prefs=None,
        domain_profile=None,
    )
    assert thin["career_readiness"]["evidence_index"] is None

    rich = ci.compose_career_intelligence(
        concept_summary=summary,
        assessment_rows=[
            {"session_id": "s1", "overall_score": 80, "questions_attempted": 8, "created_at": "a"},
            {"session_id": "s2", "overall_score": 85, "questions_attempted": 8, "created_at": "b"},
        ],
        planned_topics=[],
        project_defense_aggregate=None,
        prefs=None,
        domain_profile={"category": "programming"},
    )
    assert rich["career_readiness"]["evidence_index"] is not None
    assert "Average of last coverage" in (rich["career_readiness"]["evidence_method"] or "")


def test_declining_performance_detected():
    summary = {
        "has_data": True,
        "concepts": [
            _concept("caching", "weak", times=3, last="none", trend=["excellent", "good", "none"]),
        ],
        "history": [],
    }
    out = ci.compose_career_intelligence(
        concept_summary=summary,
        assessment_rows=[
            {"session_id": "s1", "overall_score": 90, "questions_attempted": 3, "created_at": "a"},
            {"session_id": "s2", "overall_score": 40, "questions_attempted": 3, "created_at": "b"},
        ],
        planned_topics=[],
        project_defense_aggregate=None,
        prefs=None,
        domain_profile=None,
    )
    assert "caching" in out["progress"]["declining"]


def test_compose_consumes_shared_snapshot_without_breaking_contract():
    from app.services.candidate_intelligence import compose_candidate_intelligence

    snap = compose_candidate_intelligence(
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
                "details": {"purpose": "Shop", "technologies": "FastAPI"},
                "source": "resume",
                "missing_details": ["architecture", "contribution", "outcome", "features"],
            },
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
                "planned_topics": ["Python", "Redis", "Caching"],
            }
        ],
        turn_rows=[
            {
                "session_id": "s1",
                "track_id": "t1",
                "turn_index": 1,
                "question_area": "Python",
                "answer": "good",
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
                "answer": "good2",
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
                "answer": "weak",
                "evaluation_coverage": "none",
                "evaluation_gaps": ["outer joins"],
                "evaluation_detail": {},
                "created_at": "2026-01-01T00:02:00+00:00",
            },
        ],
        report_rows=[],
    )
    # Turn aggregate for core fields (same path as production).
    summary = weakness_service.aggregate_turns(
        [
            SimpleNamespace(
                question_area="Python",
                answer="good",
                evaluation_coverage="excellent",
                evaluation_gaps=[],
                session_id="s1",
                turn_index=1,
                evaluation_detail={},
            ),
            SimpleNamespace(
                question_area="Python",
                answer="good2",
                evaluation_coverage="good",
                evaluation_gaps=[],
                session_id="s1",
                turn_index=2,
                evaluation_detail={},
            ),
            SimpleNamespace(
                question_area="SQL joins",
                answer="weak",
                evaluation_coverage="none",
                evaluation_gaps=["outer joins"],
                session_id="s1",
                turn_index=3,
                evaluation_detail={},
            ),
            SimpleNamespace(
                question_area="SQL joins",
                answer="still weak",
                evaluation_coverage="none",
                evaluation_gaps=["outer joins"],
                session_id="s2",
                turn_index=1,
                evaluation_detail={},
            ),
        ],
        session_order=["s1", "s2"],
    )
    out = ci.compose_career_intelligence(
        concept_summary=summary,
        assessment_rows=[
            {
                "session_id": "s1",
                "track_subject": "Backend",
                "overall_score": 55,
                "questions_attempted": 3,
                "created_at": "2026-01-01",
            },
            {
                "session_id": "s2",
                "track_subject": "Backend",
                "overall_score": 50,
                "questions_attempted": 2,
                "created_at": "2026-02-01",
            },
        ],
        planned_topics=["Python", "Caching"],
        project_defense_aggregate=None,
        prefs=None,  # goals should come from snapshot
        domain_profile={"category": "programming", "uses_code": True},
        focus_track_id="t1",
        candidate_intelligence=snap,
    )
    # Existing contract preserved.
    assert out["disclaimer"]
    assert out["career_readiness"]["target_role"] == "Backend Developer"
    assert out["strengths"] or out["improvement_areas"] or out["developing"]
    assert out["integrations"]["candidate_intelligence"] is True
    # Snapshot overview / projects / gaps.
    assert out["candidate_overview"]["career_goals"]["target_role"] == "Backend Developer"
    assert out["project_intelligence"]["projects"][0]["name"] == "Campus Cart"
    assert out["project_intelligence"]["projects"][0]["evidence_kind"] == "claim"
    assert "architecture" in out["project_intelligence"]["projects"][0]["needs_clarification"]
    gaps = out["knowledge_gaps"]
    assert gaps["policy"]["unknown_is_not_weak"] is True
    assert "Redis" in gaps["claimed_skills_without_interview"] or "Redis" in gaps[
        "unverified_claims"
    ]
    # Redis claim must not appear as a demonstrated weakness.
    assert not any("redis" in str(r.get("concept") or "").lower() for r in out["improvement_areas"])
    # Demonstrated Python strength should not be re-recommended.
    assert not any(r["topic"].lower() == "python" for r in out["recommendations"])
    # SQL weakness / project clarification should be recommended with evidence.
    assert any(
        "sql" in r["topic"].lower() or "join" in r["topic"].lower() or "clarify" in r["topic"].lower()
        for r in out["recommendations"]
    )
    assert any(r.get("evidence_basis") for r in out["recommendations"])
    # Track-scoped competency evidence.
    assert out["competency_evidence"]
    assert all(c["evidence_kind"] == "demonstrated" for c in out["competency_evidence"])
    assert out["progress"]["available"] is True
    assert "comparable" in (out["progress"].get("comparison_note") or "").lower()


def test_insufficient_evidence_readiness_with_snapshot_claims_only():
    from app.services.candidate_intelligence import compose_candidate_intelligence

    snap = compose_candidate_intelligence(
        user_profile=None,
        vault_items=[
            {
                "id": "1",
                "category": "skill",
                "title": "Kubernetes",
                "details": {},
                "source": "resume",
                "missing_details": [],
            }
        ],
        preferences={"interests": ["technical"], "target_role": "DevOps", "confirmed": True},
        profile_review=None,
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[],
    )
    out = ci.compose_career_intelligence(
        concept_summary={"concepts": [], "history": [], "has_data": False},
        assessment_rows=[],
        planned_topics=[],
        project_defense_aggregate=None,
        prefs=None,
        domain_profile=None,
        candidate_intelligence=snap,
    )
    assert out["career_readiness"]["level"] == "insufficient_evidence"
    assert out["progress"]["available"] is False
    assert out["knowledge_gaps"]["demonstrated_weaknesses"] == []
    assert "Kubernetes" in out["not_yet_assessed"] or "Kubernetes" in out["knowledge_gaps"][
        "claimed_skills_without_interview"
    ]
    assert out["integrations"]["candidate_intelligence"] is True


def test_empty_helper():
    empty = ci.empty_career_intelligence()
    assert empty["career_readiness"]["level"] == "insufficient_evidence"
