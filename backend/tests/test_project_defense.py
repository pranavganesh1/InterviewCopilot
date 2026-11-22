"""Phase D Feature 2: Real Project Defense Intelligence (offline / mocked)."""

from types import SimpleNamespace

from app.agents.interviewer import apply_local_policy, system_prompt_for_mode
from app.agents.question_dedupe import is_duplicate_question
from app.agents.question_quality import question_type_allowed
from app.services import probe as probe_service
from app.services.interview_service import build_covered_so_far


def _vault_item(title, *, category="project", details=None):
    return SimpleNamespace(category=category, title=title, details=details or {})


def test_project_context_extraction_known_and_missing():
    details = {
        "purpose": "Campus navigation",
        "technologies": "React, FastAPI",
        "contribution": "Built routing API",
    }
    known = probe_service.project_known_fields(details)
    assert known["purpose"].startswith("Campus")
    assert "architecture" not in known
    missing = probe_service.project_missing_fields(details)
    assert "architecture" in missing
    assert "outcome" in missing
    assert "technologies" not in missing


def test_no_fabricated_architecture_or_metrics_in_prompt_block():
    items = probe_service.sanitize_vault_items(
        [_vault_item("Line follower", details={"purpose": "Follow a line"})],
        categories=("project",),
    )
    block = probe_service.vault_prompt_block(items)
    assert "Line follower" in block
    assert "purpose=Follow a line" in block
    assert "missing_fields=" in block
    assert "architecture=" not in block.split("missing_fields=")[0]
    assert "latency" not in block.lower()
    assert "UNTRUSTED_CANDIDATE_DATA_START" in block


def test_project_specific_question_generation_and_missing_info():
    items = [
        {
            "category": "project",
            "title": "Budget tracker",
            "details": {"purpose": "Track expenses"},
        }
    ]
    probe = probe_service.craft_project_defense_probe(
        items=items, area="Projects", asked=[], mode="strict", seed=0
    )
    assert probe is not None
    assert "Budget tracker" in probe["next_question"]
    assert probe["notes_for_report"] == "resume_probe"
    # Missing architecture/tech/contribution/outcome should be askable.
    assert any(
        word in probe["next_question"].lower()
        for word in ("architecture", "technologies", "stack", "contribution", "implement", "evaluate")
    )


def test_ownership_dimension_question():
    items = [
        {
            "category": "project",
            "title": "Sensor hub",
            "details": {
                "purpose": "Collect sensor data",
                "technologies": "Arduino",
                "architecture": "MCU + BLE",
                "contribution": "Firmware",
                "outcome": "Demo day",
            },
        }
    ]
    # With no missing fields, seed 7 maps to ownership in _DEFENSE_TEMPLATES.
    probe = probe_service.craft_project_defense_probe(
        items=items, area="Projects", asked=[], mode="strict", seed=7
    )
    assert probe is not None
    assert "personally" in probe["next_question"].lower() or "others" in probe["next_question"].lower()


def test_defense_follow_up_reuses_adaptive_policy():
    from app.agents.interviewer import TurnDecision

    d = TurnDecision.model_validate(
        {
            "evaluation": {"coverage": "partial", "strengths": [], "gaps": ["unclear trade-off"]},
            "decision": "next_area",
            "next_question": "What trade-off did MongoDB give your data model?",
            "question_area": "Budget tracker",
            "notes_for_report": "ok",
        }
    )
    fixed = apply_local_policy(
        d,
        {
            "turns_in_current_area": 1,
            "current_area": "Budget tracker",
            "remaining_areas": ["Sensor hub"],
            "last_answer": "It stores JSON",
            "questions_remaining": 10,
            "defense_mode": True,
        },
    )
    assert fixed.decision == "follow_up"
    assert fixed.question_area == "Budget tracker"


def test_merge_defense_prefers_projects_without_inventing():
    track = [{"topic": "DBMS", "guidance": "indexes"}, {"topic": "OS", "guidance": "scheduling"}]
    projects = [{"topic": "Campus nav", "guidance": "Project defense"}]
    merged = probe_service.merge_defense_question_areas(track, projects, cap=12, track_keep=4)
    assert merged[0]["topic"] == "Campus nav"
    assert {a["topic"] for a in merged} >= {"Campus nav", "DBMS"}
    empty = probe_service.merge_defense_question_areas(track, [], cap=12)
    assert empty == track


def test_candidates_without_projects_keep_normal_plan_bias_noop():
    plan = [{"topic": "Mechanics", "objective": "Newton", "difficulty": "foundational"}]
    assert probe_service.bias_plan_for_defense(plan, []) == plan


def test_bias_plan_for_defense_rewrites_objectives():
    plan = [
        {"topic": "DBMS", "objective": "indexes", "difficulty": "intermediate"},
        {"topic": "OS", "objective": "scheduling", "difficulty": "intermediate"},
    ]
    biased = probe_service.bias_plan_for_defense(plan, ["Campus nav", "Sensor hub"])
    assert biased[0]["topic"] == "Campus nav"
    assert "Project defense" in biased[0]["objective"]
    assert biased[1]["topic"] == "Sensor hub"


def test_no_duplicate_project_questions():
    asked = ["In your project Campus nav, why that design instead of a simpler alternative?"]
    items = [{"category": "project", "title": "Campus nav", "details": {}}]
    probe = probe_service.craft_resume_probe(
        items=items,
        area="Campus nav",
        asked=asked,
        mode="strict",
        seed=0,
        defense_mode=True,
    )
    # May be None (deduped) or a different dimension question.
    if probe:
        assert not is_duplicate_question(probe["next_question"], asked[0])


def test_domain_safety_still_blocks_coding_for_science():
    payload = {
        "domain_profile": {
            "category": "science",
            "uses_code": False,
            "allowed_types": ["conceptual", "numeric", "scenario"],
        },
        "allowed_types": ["conceptual", "numeric", "scenario"],
        "defense_mode": True,
    }
    assert not question_type_allowed("coding", payload)
    assert question_type_allowed("conceptual", payload)


def test_strict_vs_guided_preserved_with_defense_rules():
    strict = system_prompt_for_mode("strict").lower()
    guided = system_prompt_for_mode("guided").lower()
    assert "hint" in strict and "never" in strict
    assert "assistance" in guided or "hint" in guided
    rules = probe_service.defense_system_rules().lower()
    assert "never invent" in rules or "never invent them" in rules
    assert "accuse" in rules or "authorship" in rules


def test_session_opts_persist_defense_mode():
    plan = [{"topic": "X", "objective": "y"}]
    plan = probe_service.attach_session_opts(
        plan,
        use_resume=True,
        focus_weak=False,
        defense_mode=True,
        include_vault_topics=True,
    )
    opts = probe_service.session_opts_from_plan(plan)
    assert opts["defense_mode"] is True
    assert probe_service.personalize_from_vault(opts) is True


def test_project_defense_findings_from_turns():
    turns = [
        SimpleNamespace(
            answer="I built the API",
            question_area="Campus nav",
            question="Which parts did you personally implement?",
            evaluation_coverage="good",
            evaluation_gaps=[],
            evaluation_detail={
                "question_meta": {
                    "origin": "resume_probe",
                    "project_name": "Campus nav",
                    "objective": "Campus nav::ownership",
                }
            },
        ),
        SimpleNamespace(
            answer="not sure",
            question_area="Campus nav",
            question="Explain architecture",
            evaluation_coverage="partial",
            evaluation_gaps=["missing component boundaries"],
            evaluation_detail={
                "question_meta": {
                    "origin": "resume_probe",
                    "project_name": "Campus nav",
                    "objective": "Campus nav::architecture",
                }
            },
        ),
    ]
    findings = probe_service.project_defense_findings(turns)
    assert findings["has_data"]
    assert "Campus nav" in findings["projects_assessed"]
    assert findings["knowledge_gaps"]
    assert any("ownership" in d for d in findings["demonstrated"])


def test_knowledge_state_still_works_alongside_defense():
    turns = [
        SimpleNamespace(
            question_area="Campus nav",
            question="Why React?",
            answer="component model",
            evaluation_coverage="good",
            evaluation_gaps=[],
        )
    ]
    mem = build_covered_so_far(
        turns,
        plan=[{"topic": "Campus nav", "objective": "tech", "difficulty": "intermediate"}],
        questions_asked=1,
    )
    assert "Campus nav" in mem["knowledge_state"]["demonstrated_strengths"]


def test_vault_plan_areas_projects_only():
    items = [
        _vault_item("A project"),
        _vault_item("Python", category="skill"),
        _vault_item("Intern role", category="internship"),
    ]
    areas = probe_service.vault_plan_areas(items, limit=8, categories=("project",))
    assert len(areas) == 1
    assert areas[0]["topic"] == "A project"
