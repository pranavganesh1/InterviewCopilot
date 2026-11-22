"""Career Readiness Intelligence — deterministic aggregation only (no AI agent).

Composes stored interview evaluations, Adaptive Knowledge (weakness/knowledge),
Project Defense findings, vault readiness claim summaries, and preparation
preferences. Never invents role requirements or guarantees outcomes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.services import probe as probe_service
from app.services import weakness as weakness_service

_COVERAGE_POINTS = {"none": 0, "partial": 50, "good": 75, "excellent": 100}
_MIN_QUESTIONS_FOR_EVIDENCE_INDEX = 8
_MIN_SESSIONS_FOR_PROGRESS = 2

_DISCIPLINE_PRACTICE = {
    "programming": "Solve one short problem aloud and explain trade-offs.",
    "science": "Derive the result from stated assumptions on paper.",
    "business": "Walk through a numeric example from a realistic case.",
    "healthcare": "Explain the clinical or process rationale for a key decision.",
    "general": "Explain the concept with a concrete example from your work.",
}

_DISCLAIMER = (
    "Based on completed interview evidence only. This is preparation guidance, "
    "not a hiring prediction. Concepts not yet assessed are listed separately "
    "and are not treated as failures."
)


def evidence_label(status: str, times_asked: int) -> str:
    """Map concept aggregate status to Feature 3 evidence buckets."""
    if times_asked < 1 or status == "not_enough_data":
        return "insufficient_evidence"
    if status == "mastered":
        return "demonstrated_strength"
    if status == "weak":
        return "demonstrated_weakness"
    if status == "improving":
        return "developing"
    return "insufficient_evidence"


def _discipline_key(domain_profile: dict | None, prefs: dict | None) -> str:
    if isinstance(domain_profile, dict):
        cat = str(domain_profile.get("category") or "").lower()
        if cat in _DISCIPLINE_PRACTICE:
            return cat
        if domain_profile.get("uses_code"):
            return "programming"
    interests = list((prefs or {}).get("interests") or [])
    joined = " ".join(str(i).lower() for i in interests)
    if any(k in joined for k in ("software", "coding", "dsa", "tech", "cs")):
        return "programming"
    if any(k in joined for k in ("physics", "chem", "bio", "science")):
        return "science"
    if any(k in joined for k in ("commerce", "finance", "account", "business")):
        return "business"
    return "general"


def _dedupe_preserve(items: list[str], *, limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        text = " ".join(str(raw or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:160])
        if len(out) >= limit:
            break
    return out


def build_concept_intelligence(summary: dict) -> dict:
    """Strengths / weaknesses / developing from weakness.aggregate_turns."""
    strengths: list[dict] = []
    weaknesses: list[dict] = []
    developing: list[dict] = []
    insufficient: list[dict] = []
    for row in summary.get("concepts") or []:
        if not isinstance(row, dict):
            continue
        concept = str(row.get("concept") or "").strip()
        if not concept:
            continue
        times = int(row.get("times_asked") or 0)
        status = str(row.get("status") or "not_enough_data")
        label = evidence_label(status, times)
        entry = {
            "concept": concept,
            "status": status,
            "evidence_label": label,
            "times_asked": times,
            "last_coverage": row.get("last_coverage"),
            "trend": list(row.get("trend") or [])[-3:],
            "missing_concepts": list(row.get("missing_concepts") or [])[:4],
            "evidence": list(row.get("evidence") or [])[:3],
        }
        if label == "demonstrated_strength":
            strengths.append(entry)
        elif label == "demonstrated_weakness":
            weaknesses.append(entry)
        elif label == "developing":
            developing.append(entry)
        else:
            insufficient.append(entry)
    return {
        "demonstrated_strengths": strengths[:10],
        "demonstrated_weaknesses": weaknesses[:10],
        "developing": developing[:10],
        "insufficient_evidence": insufficient[:10],
    }


def build_progress(
    *,
    session_count: int,
    concept_summary: dict,
    assessment_scores: list[dict],
) -> dict:
    """Chronological progress. One interview → no over-time narrative."""
    if session_count < _MIN_SESSIONS_FOR_PROGRESS:
        return {
            "available": False,
            "reason": (
                "Complete at least two interviews to see progress over time."
                if session_count == 1
                else "No completed interviews yet."
            ),
            "improving": [],
            "declining": [],
            "consistent_strengths": [],
            "persistent_weaknesses": [],
            "session_score_trend": [],
        }

    improving = [
        c["concept"]
        for c in (concept_summary.get("concepts") or [])
        if isinstance(c, dict) and c.get("status") == "improving"
    ][:8]
    persistent = [
        c["concept"]
        for c in (concept_summary.get("concepts") or [])
        if isinstance(c, dict) and c.get("status") == "weak" and int(c.get("times_asked") or 0) >= 2
    ][:8]
    consistent = [
        c["concept"]
        for c in (concept_summary.get("concepts") or [])
        if isinstance(c, dict) and c.get("status") == "mastered"
    ][:8]

    declining: list[str] = []
    for c in concept_summary.get("concepts") or []:
        if not isinstance(c, dict):
            continue
        trend = [str(x).lower() for x in (c.get("trend") or [])]
        if len(trend) >= 2 and trend[-1] in ("none", "partial") and trend[0] in (
            "good",
            "excellent",
        ):
            declining.append(str(c.get("concept") or ""))
    declining = _dedupe_preserve(declining, limit=6)

    score_trend = [
        {
            "session_id": row.get("session_id"),
            "track_subject": row.get("track_subject"),
            "overall_score": row.get("overall_score"),
            "created_at": row.get("created_at"),
        }
        for row in assessment_scores
        if row.get("overall_score") is not None
    ][-8:]

    return {
        "available": True,
        "reason": "",
        "improving": _dedupe_preserve(improving),
        "declining": declining,
        "consistent_strengths": _dedupe_preserve(consistent),
        "persistent_weaknesses": _dedupe_preserve(persistent),
        "session_score_trend": score_trend,
        "area_score_history": list(concept_summary.get("history") or [])[-6:],
    }


def build_not_yet_assessed(
    planned_topics: list[str],
    assessed_concepts: set[str],
) -> list[str]:
    """Topics from briefs/plans never seen in answered evaluations."""
    out: list[str] = []
    assessed_norm = {weakness_service.normalize_concept(c) for c in assessed_concepts}
    for topic in planned_topics:
        text = (topic or "").strip()
        key = weakness_service.normalize_concept(text)
        if not key or key in assessed_norm:
            continue
        # Soft containment: skip if a longer assessed concept already covers it.
        if any(key in a or a in key for a in assessed_norm if len(a) >= 4):
            continue
        out.append(text[:80])
        if len(out) >= 12:
            break
    return out


def assess_career_readiness(
    *,
    completed_interviews: int,
    questions_assessed: int,
    concept_intel: dict,
    project_defense: dict | None,
    target_role: str | None,
    discipline: str,
) -> dict:
    """Qualitative readiness vs target role. No employment guarantee."""
    strengths_n = len(concept_intel.get("demonstrated_strengths") or [])
    weak_n = len(concept_intel.get("demonstrated_weaknesses") or [])
    developing_n = len(concept_intel.get("developing") or [])
    defense = project_defense if isinstance(project_defense, dict) else {}
    defense_gaps = len(defense.get("knowledge_gaps") or [])
    ownership_unclear = len(defense.get("ownership_unclear") or [])

    if completed_interviews < 1 or questions_assessed < 1:
        level = "insufficient_evidence"
        summary = (
            "Not enough completed interview evidence yet. Finish an interview "
            "with answered questions to assess preparation."
        )
    elif completed_interviews == 1 and questions_assessed < 5:
        level = "early"
        summary = (
            "Early signal only — one short assessment. Treat strengths as provisional "
            "and keep practising target topics."
        )
    elif weak_n >= 3 and strengths_n <= 1:
        level = "needs_focused_practice"
        summary = (
            "Several demonstrated weaknesses relative to assessed topics. "
            "Prioritise the roadmap below before expanding coverage."
        )
    elif strengths_n >= 3 and weak_n <= 1 and defense_gaps <= 1 and ownership_unclear == 0:
        level = "strong_evidence"
        summary = (
            "Multiple concepts demonstrated strongly with few open gaps"
            + (f" for {target_role}." if target_role else ".")
            + " Continue defending projects and retesting weak spots."
        )
    elif strengths_n >= 1 and (weak_n >= 1 or developing_n >= 1):
        level = "developing"
        summary = (
            "Mixed evidence: some demonstrated strengths and open gaps. "
            "Follow the preparation roadmap in priority order."
        )
    else:
        level = "building"
        summary = (
            "Building evidence across interviews. Expand coverage of not-yet-assessed "
            "topics relevant to your goal."
        )

    evidence_index = None
    evidence_method = None
    if (
        completed_interviews >= 2
        and questions_assessed >= _MIN_QUESTIONS_FOR_EVIDENCE_INDEX
    ):
        points: list[int] = []
        for bucket in (
            "demonstrated_strengths",
            "demonstrated_weaknesses",
            "developing",
        ):
            for row in concept_intel.get(bucket) or []:
                cov = str(row.get("last_coverage") or "").lower()
                if cov in _COVERAGE_POINTS:
                    points.append(_COVERAGE_POINTS[cov])
        if points:
            evidence_index = int(round(sum(points) / len(points)))
            evidence_method = (
                "Average of last coverage labels on assessed concepts "
                f"(none=0, partial=50, good=75, excellent=100); n={len(points)}. "
                "This is evidence strength, not a hiring score."
            )

    return {
        "level": level,
        "summary": summary,
        "target_role": target_role or None,
        "discipline": discipline,
        "evidence_index": evidence_index,
        "evidence_method": evidence_method,
        "disclaimer": _DISCLAIMER,
        "counts": {
            "completed_interviews": completed_interviews,
            "questions_assessed": questions_assessed,
            "demonstrated_strengths": strengths_n,
            "demonstrated_weaknesses": weak_n,
            "developing": developing_n,
            "project_defense_gaps": defense_gaps,
        },
    }


def build_recommendations(
    *,
    concept_intel: dict,
    project_defense: dict | None,
    discipline: str,
    claim_seeds: list[dict] | None = None,
    progress: dict | None = None,
    candidate_intelligence: dict | None = None,
) -> list[dict]:
    """Personalized recommendations with why + evidence + next practice."""
    practice = _DISCIPLINE_PRACTICE.get(discipline, _DISCIPLINE_PRACTICE["general"])
    out: list[dict] = []
    seen: set[str] = set()
    # Do not re-recommend topics already demonstrated strongly.
    skip = {
        str(row.get("concept") or "").lower()
        for row in (concept_intel.get("demonstrated_strengths") or [])
        if isinstance(row, dict) and row.get("concept")
    }
    if isinstance(candidate_intelligence, dict):
        demo = (candidate_intelligence.get("knowledge_evidence") or {}).get(
            "interview_demonstrated"
        ) or {}
        for row in demo.get("strengths") or []:
            if isinstance(row, dict) and row.get("concept"):
                skip.add(str(row["concept"]).lower())

    def add(
        topic: str,
        why: str,
        evidence: str,
        activity: str | None = None,
        *,
        evidence_basis: dict | None = None,
        track_subject: str | None = None,
        priority: str | None = None,
    ) -> None:
        key = topic.lower()
        if not topic or key in seen or key in skip:
            return
        seen.add(key)
        row = {
            "topic": topic[:120],
            "why": why[:240],
            "evidence": evidence[:240],
            "practice": (activity or practice)[:240],
            "expected_outcome": f"Clearer explanations of {topic[:80]} under interview pressure.",
        }
        if evidence_basis:
            row["evidence_basis"] = evidence_basis
        if track_subject:
            row["track_subject"] = track_subject
        if priority:
            row["priority"] = priority
        out.append(row)

    for row in concept_intel.get("demonstrated_weaknesses") or []:
        concept = str(row.get("concept") or "")
        gaps = ", ".join(row.get("missing_concepts") or [])[:120]
        trend = " → ".join(str(x) for x in (row.get("trend") or [])[-3:])
        add(
            concept,
            "Repeated weak coverage on this concept in completed interviews.",
            f"status={row.get('status')}; last={row.get('last_coverage')}; trend={trend}"
            + (f"; gaps={gaps}" if gaps else ""),
            evidence_basis={
                "kind": "demonstrated_weakness",
                "source": "interview_turns",
            },
            priority="high",
        )
        if len(out) >= 6:
            break

    persistent = list((progress or {}).get("persistent_weaknesses") or [])
    for concept in persistent:
        add(
            concept,
            "Persistent weakness across multiple attempts.",
            "Appears weak with times_asked ≥ 2.",
            evidence_basis={
                "kind": "persistent_weakness",
                "source": "interview_turns",
            },
            priority="high",
        )
        if len(out) >= 8:
            break

    defense = project_defense if isinstance(project_defense, dict) else {}
    for gap in list(defense.get("knowledge_gaps") or [])[:3]:
        add(
            str(gap)[:120],
            "Project-defense evaluation identified this gap.",
            "diagnostics.project_defense.knowledge_gaps",
            "Rehearse architecture, trade-offs, and personal ownership for this project.",
            evidence_basis={
                "kind": "project_defense",
                "source": "feedback_or_turns",
            },
            priority="high",
        )
    for project in list(defense.get("ownership_unclear") or [])[:2]:
        add(
            f"Ownership: {project}",
            "Ownership explanations were unclear during project defense.",
            "diagnostics.project_defense.ownership_unclear",
            f"Write which modules of {project} you personally implemented and why.",
            evidence_basis={
                "kind": "project_defense_ownership",
                "source": "feedback_or_turns",
                "project": str(project)[:80],
            },
            priority="medium",
        )

    # Vault project claims that still need clarification (not interview weaknesses).
    if isinstance(candidate_intelligence, dict):
        for proj in (candidate_intelligence.get("projects") or [])[:4]:
            if not isinstance(proj, dict) or not proj.get("name"):
                continue
            missing = list(proj.get("needs_clarification") or [])
            if not missing:
                continue
            name = str(proj["name"])
            add(
                f"Clarify: {name}",
                (
                    f"Vault project details are incomplete ({', '.join(missing[:3])}) "
                    "— clarify before treating this as interview-ready evidence."
                ),
                "candidate_intelligence.projects.needs_clarification",
                f"Fill in {', '.join(missing[:3])} for {name}, then practise a project defense.",
                evidence_basis={
                    "kind": "vault_project_claim",
                    "project": name,
                    "needs_clarification": missing[:6],
                },
                priority="medium",
            )
            if len(out) >= 8:
                break

    for seed in (claim_seeds or [])[:2]:
        if not isinstance(seed, dict):
            continue
        claim = str(seed.get("claim") or "").strip()
        title = str(seed.get("title") or "vault claim").strip()
        if claim:
            add(
                title,
                "Resume readiness flagged this claim for interview preparation "
                "(claim, not demonstrated ability).",
                claim[:160],
                "Practise answering follow-ups about scope, method, and personal role.",
                evidence_basis={
                    "kind": "vault_claim",
                    "source": "readiness_claim_seeds",
                },
                priority="explore",
            )

    return out[:8]


def build_roadmap(
    recommendations: list[dict],
    *,
    not_yet_assessed: list[str],
    target_role: str | None,
) -> list[dict]:
    """Ordered preparation steps — not a calendar unless timeline was provided."""
    steps: list[dict] = []
    for i, rec in enumerate(recommendations[:6], start=1):
        steps.append(
            {
                "order": i,
                "topic": rec.get("topic"),
                "reason": rec.get("why"),
                "activity": rec.get("practice"),
                "expected_outcome": rec.get("expected_outcome"),
                "priority": "high" if i <= 2 else "medium",
            }
        )
    # Append not-yet-assessed as lower priority exploration (not weaknesses).
    base = len(steps)
    for j, topic in enumerate(not_yet_assessed[:4], start=1):
        steps.append(
            {
                "order": base + j,
                "topic": topic,
                "reason": (
                    f"Relevant to {target_role} but not yet assessed in interviews."
                    if target_role
                    else "Relevant track topic not yet assessed in interviews."
                ),
                "activity": "Schedule a short practice interview covering this topic.",
                "expected_outcome": "Evidence for this topic instead of an unknown.",
                "priority": "explore",
            }
        )
    return steps


def build_next_actions(
    *,
    readiness_level: str,
    recommendations: list[dict],
    focus_track_id: str | None,
    has_projects: bool,
) -> list[dict]:
    actions: list[dict] = []
    if readiness_level == "insufficient_evidence":
        actions.append(
            {
                "kind": "start_interview",
                "title": "Complete your first interview",
                "reason": "Career readiness needs answered-question evidence.",
                "action_label": "Start interview",
                "href": focus_track_id and f"/tracks/{focus_track_id}" or "/",
            }
        )
        return actions
    if recommendations and focus_track_id:
        topic = recommendations[0].get("topic")
        actions.append(
            {
                "kind": "practice_weak",
                "title": f"Practise: {topic}",
                "reason": recommendations[0].get("why") or "Top demonstrated gap.",
                "action_label": "Practice weak areas",
                "track_id": focus_track_id,
                "href": f"/tracks/{focus_track_id}",
            }
        )
    if has_projects and focus_track_id:
        actions.append(
            {
                "kind": "defend_projects",
                "title": "Defend your projects",
                "reason": "Strengthen architecture and ownership explanations.",
                "action_label": "Defend my projects",
                "track_id": focus_track_id,
                "href": f"/tracks/{focus_track_id}",
            }
        )
    actions.append(
        {
            "kind": "vault_readiness",
            "title": "Review resume claims",
            "reason": "Prepare answers for claims interviewers often probe.",
            "action_label": "Open readiness",
            "href": "/readiness",
        }
    )
    return actions[:3]


def _overview_from_snapshot(snapshot: dict | None, prefs: dict | None) -> dict | None:
    if not isinstance(snapshot, dict):
        return None
    profile = snapshot.get("profile") or {}
    vault = profile.get("vault") or {}
    goals = profile.get("career_goals") or {}
    prefs_n = prefs if isinstance(prefs, dict) else {}
    return {
        "education": list(vault.get("education") or [])[:8],
        "skills": list(vault.get("skills") or [])[:12],
        "internships": list(vault.get("internships") or [])[:8],
        "projects": [
            {"id": p.get("id"), "title": p.get("title"), "source": p.get("source")}
            for p in (vault.get("projects") or [])[:8]
            if isinstance(p, dict)
        ],
        "career_goals": {
            "target_role": goals.get("target_role") or prefs_n.get("target_role"),
            "interests": list(goals.get("interests") or prefs_n.get("interests") or []),
            "technical_areas": list(
                goals.get("technical_areas") or prefs_n.get("technical_areas") or []
            )[:8],
            "focus_projects": list(
                goals.get("focus_projects") or prefs_n.get("focus_projects") or []
            )[:6],
            "evidence_kind": "preference",
        },
        "user_profile": profile.get("user_profile"),
        "source_conflicts": list(profile.get("source_conflicts") or []),
        "source": "candidate_intelligence_snapshot",
    }


def _competency_evidence_from_snapshot(snapshot: dict | None) -> list[dict]:
    """Track-scoped demonstrated competencies with provenance (claims excluded)."""
    if not isinstance(snapshot, dict):
        return []
    out: list[dict] = []
    knowledge = snapshot.get("knowledge_evidence") or {}
    for track in knowledge.get("by_track") or []:
        if not isinstance(track, dict):
            continue
        tid = track.get("track_id")
        subject = track.get("track_subject")
        for row in track.get("concepts") or []:
            if not isinstance(row, dict) or not row.get("concept"):
                continue
            evidence = list(row.get("evidence") or [])[:3]
            out.append(
                {
                    "competency": str(row["concept"])[:80],
                    "assessment": row.get("status"),
                    "evidence_kind": "demonstrated",
                    "evidence_source": "interview_turns",
                    "track_id": tid,
                    "track_subject": subject,
                    "times_asked": row.get("times_asked"),
                    "last_coverage": row.get("last_coverage"),
                    "trend": list(row.get("trend") or [])[-3:],
                    "evidence": evidence,
                    "freshness": {
                        "note": (
                            "Based on answered interview turns for this track. "
                            "Not a hiring guarantee."
                        ),
                        "session_ids": [
                            e.get("session_id")
                            for e in evidence
                            if isinstance(e, dict) and e.get("session_id")
                        ][:3],
                    },
                }
            )
            if len(out) >= 40:
                return out
    return out


def _knowledge_gaps_from_snapshot(
    snapshot: dict | None,
    *,
    concept_intel: dict,
    not_yet_assessed: list[str],
) -> dict:
    """Separate demonstrated weakness / developing / not assessed / claims."""
    demo_weak = [
        {
            "concept": row.get("concept"),
            "status": "demonstrated_weakness",
            "times_asked": row.get("times_asked"),
            "last_coverage": row.get("last_coverage"),
            "evidence_kind": "demonstrated",
        }
        for row in (concept_intel.get("demonstrated_weaknesses") or [])
        if isinstance(row, dict) and row.get("concept")
    ][:10]
    developing = [
        {
            "concept": row.get("concept"),
            "status": "needs_improvement",
            "times_asked": row.get("times_asked"),
            "last_coverage": row.get("last_coverage"),
            "evidence_kind": "demonstrated",
        }
        for row in (concept_intel.get("developing") or [])
        if isinstance(row, dict) and row.get("concept")
    ][:10]
    insufficient = [
        {
            "concept": row.get("concept"),
            "status": "insufficient_evidence",
            "evidence_kind": "demonstrated",
        }
        for row in (concept_intel.get("insufficient_evidence") or [])
        if isinstance(row, dict) and row.get("concept")
    ][:10]

    unverified: list[str] = []
    claimed_without: list[str] = []
    track_gaps: list[dict] = []
    if isinstance(snapshot, dict):
        knowledge = snapshot.get("knowledge_evidence") or {}
        claims = knowledge.get("candidate_claims") or {}
        not_assessed = knowledge.get("not_assessed") or {}
        unverified = [
            str(s.get("title") or "")[:80]
            for s in (claims.get("skills") or [])
            if isinstance(s, dict) and s.get("title")
        ][:12]
        claimed_without = list(
            not_assessed.get("claimed_skills_without_interview") or []
        )[:12]
        for track in knowledge.get("by_track") or []:
            if not isinstance(track, dict):
                continue
            track_gaps.append(
                {
                    "track_id": track.get("track_id"),
                    "track_subject": track.get("track_subject"),
                    "demonstrated_weaknesses": [
                        r.get("concept")
                        for r in (track.get("demonstrated_weaknesses") or [])
                        if isinstance(r, dict) and r.get("concept")
                    ][:6],
                    "not_assessed": list(track.get("not_assessed") or [])[:8],
                    "scope": "track",
                }
            )
            if len(track_gaps) >= 8:
                break

    return {
        "demonstrated_weaknesses": demo_weak,
        "needs_improvement": developing,
        "insufficient_evidence": insufficient,
        "not_assessed": list(not_yet_assessed or [])[:12],
        "unverified_claims": unverified,
        "claimed_skills_without_interview": claimed_without,
        "by_track": track_gaps,
        "policy": {
            "unknown_is_not_weak": True,
            "claims_are_not_proof": True,
            "note": (
                "Not-assessed and unverified claims are not weaknesses. "
                "Demonstrated weaknesses come only from answered interview turns."
            ),
        },
    }


def _project_intelligence_from_snapshot(snapshot: dict | None) -> dict | None:
    if not isinstance(snapshot, dict):
        return None
    projects = []
    for proj in snapshot.get("projects") or []:
        if not isinstance(proj, dict) or not proj.get("name"):
            continue
        projects.append(
            {
                "name": proj.get("name"),
                "technologies": proj.get("technologies"),
                "contribution": proj.get("contribution"),
                "architecture": proj.get("architecture"),
                "outcomes": proj.get("outcomes"),
                "needs_clarification": list(proj.get("needs_clarification") or [])[:6],
                "discussion_ready": not bool(proj.get("needs_clarification")),
                "evidence_kind": "claim",
            }
        )
        if len(projects) >= 8:
            break
    vault = (snapshot.get("profile") or {}).get("vault") or {}
    return {
        "projects": projects,
        "internships": list(vault.get("internships") or [])[:8],
        "source": "candidate_intelligence_snapshot",
        "note": "Project details are candidate claims until defended in an interview.",
    }


def compose_career_intelligence(
    *,
    concept_summary: dict,
    assessment_rows: list[dict],
    planned_topics: list[str],
    project_defense_aggregate: dict | None,
    prefs: dict | None,
    domain_profile: dict | None,
    claim_seeds: list[dict] | None = None,
    focus_track_id: str | None = None,
    has_projects: bool = False,
    adaptive_knowledge_samples: list[dict] | None = None,
    candidate_intelligence: dict | None = None,
) -> dict:
    """Pure composer used by API and offline tests.

    When ``candidate_intelligence`` is provided, overview / project / gap
    sections and recommendation filtering reuse the shared snapshot. Core
    strengths/improvement_areas/progress remain driven by interview-turn aggregates.
    """
    snap = candidate_intelligence if isinstance(candidate_intelligence, dict) else None
    # Prefer snapshot goals when caller prefs are empty.
    if snap and not prefs:
        goals = (snap.get("profile") or {}).get("career_goals")
        if isinstance(goals, dict):
            prefs = {
                "interests": list(goals.get("interests") or []),
                "target_role": goals.get("target_role"),
                "technical_areas": list(goals.get("technical_areas") or []),
                "focus_skills": list(goals.get("focus_skills") or []),
                "focus_projects": list(goals.get("focus_projects") or []),
                "placement_target": goals.get("placement_target"),
                "experience_level": goals.get("experience_level"),
                "behavioral_goals": goals.get("behavioral_goals"),
                "confirmed": bool(goals.get("confirmed")),
            }
    if snap and not has_projects:
        has_projects = bool(snap.get("projects"))

    # Merge planned topics with snapshot not-assessed brief topics (deduped).
    planned = list(planned_topics or [])
    if snap:
        not_assessed_block = (snap.get("knowledge_evidence") or {}).get("not_assessed") or {}
        for topic in not_assessed_block.get("from_briefs_cross_track") or []:
            planned.append(str(topic))
        planned = _dedupe_preserve(planned, limit=40)

    concept_intel = build_concept_intelligence(concept_summary)
    completed = len(
        [r for r in assessment_rows if not r.get("track_archived") and r.get("session_id")]
    )
    # Prefer unique session ids.
    session_ids = {
        str(r.get("session_id"))
        for r in assessment_rows
        if r.get("session_id") and not r.get("track_archived")
    }
    completed = len(session_ids) or completed

    questions_assessed = sum(
        int(r.get("questions_attempted") or 0)
        for r in assessment_rows
        if not r.get("track_archived")
    )
    # Deduplicate follow-up inflation: prefer concept times from aggregate.
    concept_asks = sum(
        int(c.get("times_asked") or 0) for c in (concept_summary.get("concepts") or [])
    )
    if concept_asks:
        questions_assessed = max(questions_assessed, concept_asks)

    assessed_names = {
        str(c.get("concept") or "")
        for c in (concept_summary.get("concepts") or [])
        if isinstance(c, dict) and c.get("concept")
    }
    not_yet = build_not_yet_assessed(planned, assessed_names)
    # Also surface claimed skills without interview as not-yet (not weaknesses).
    if snap:
        claimed_missing = list(
            ((snap.get("knowledge_evidence") or {}).get("not_assessed") or {}).get(
                "claimed_skills_without_interview"
            )
            or []
        )
        not_yet = _dedupe_preserve([*not_yet, *claimed_missing], limit=16)

    progress = build_progress(
        session_count=completed,
        concept_summary=concept_summary,
        assessment_scores=sorted(
            assessment_rows,
            key=lambda r: str(r.get("created_at") or ""),
        ),
    )
    # Clarify progress availability without inventing improvement claims.
    if isinstance(progress, dict) and not progress.get("available"):
        progress = {
            **progress,
            "comparison_note": (
                progress.get("reason")
                or "Comparable multi-interview evidence is not available yet."
            ),
        }
    else:
        progress = {
            **progress,
            "comparison_note": (
                "Progress uses comparable concept coverage trends across completed "
                "interviews only — unrelated scores are not compared."
            ),
        }

    discipline = _discipline_key(domain_profile, prefs)
    target_role = None
    if isinstance(prefs, dict):
        target_role = (prefs.get("target_role") or prefs.get("placement_target") or None)
        if isinstance(target_role, str):
            target_role = target_role.strip() or None

    readiness = assess_career_readiness(
        completed_interviews=completed,
        questions_assessed=questions_assessed,
        concept_intel=concept_intel,
        project_defense=project_defense_aggregate,
        target_role=target_role,
        discipline=discipline,
    )
    recommendations = build_recommendations(
        concept_intel=concept_intel,
        project_defense=project_defense_aggregate,
        discipline=discipline,
        claim_seeds=claim_seeds,
        progress=progress,
        candidate_intelligence=snap,
    )
    roadmap = build_roadmap(
        recommendations, not_yet_assessed=not_yet, target_role=target_role
    )
    # Attach supporting evidence / track hints onto roadmap when present on recs.
    rec_by_topic = {
        str(r.get("topic") or "").lower(): r for r in recommendations if r.get("topic")
    }
    enriched_roadmap = []
    for step in roadmap:
        topic_key = str(step.get("topic") or "").lower()
        rec = rec_by_topic.get(topic_key)
        row = dict(step)
        if rec:
            if rec.get("evidence_basis") and "evidence_basis" not in row:
                row["evidence_basis"] = rec["evidence_basis"]
            if rec.get("track_subject"):
                row["track_subject"] = rec["track_subject"]
            if rec.get("evidence") and "supporting_evidence" not in row:
                row["supporting_evidence"] = rec["evidence"]
        elif row.get("priority") == "explore":
            row["evidence_basis"] = {
                "kind": "not_assessed",
                "source": "planned_or_claimed",
            }
        enriched_roadmap.append(row)

    next_actions = build_next_actions(
        readiness_level=str(readiness.get("level") or ""),
        recommendations=recommendations,
        focus_track_id=focus_track_id,
        has_projects=has_projects,
    )

    return {
        "disclaimer": _DISCLAIMER,
        "career_readiness": readiness,
        "strengths": concept_intel["demonstrated_strengths"],
        "improvement_areas": concept_intel["demonstrated_weaknesses"],
        "developing": concept_intel["developing"],
        "not_yet_assessed": not_yet,
        "progress": progress,
        "recommendations": recommendations,
        "roadmap": enriched_roadmap,
        "next_actions": next_actions,
        "project_defense": project_defense_aggregate
        if (project_defense_aggregate or {}).get("has_data")
        else None,
        "adaptive_knowledge": {
            "samples": list(adaptive_knowledge_samples or [])[:5],
            "integrated": bool(concept_summary.get("has_data")),
        },
        "integrations": {
            "adaptive_knowledge": bool(concept_summary.get("has_data")),
            "project_defense": bool((project_defense_aggregate or {}).get("has_data")),
            "vault_claims": bool(claim_seeds) or bool(snap and snap.get("projects")),
            "preparation_preferences": bool(prefs),
            "candidate_intelligence": bool(snap),
        },
        # Optional shared-snapshot sections (ignored by older clients).
        "candidate_overview": _overview_from_snapshot(snap, prefs),
        "competency_evidence": _competency_evidence_from_snapshot(snap),
        "knowledge_gaps": _knowledge_gaps_from_snapshot(
            snap, concept_intel=concept_intel, not_yet_assessed=not_yet
        ),
        "project_intelligence": _project_intelligence_from_snapshot(snap),
    }


def empty_career_intelligence(*, reason: str | None = None) -> dict:
    return compose_career_intelligence(
        concept_summary={"concepts": [], "history": [], "has_data": False},
        assessment_rows=[],
        planned_topics=[],
        project_defense_aggregate=None,
        prefs=None,
        domain_profile=None,
    )


async def _user_answered_turns(db: AsyncSession, user_id) -> tuple[list, list]:
    """All answered turns for the user (oldest first) + session id order."""
    rows = (
        await db.execute(
            select(SessionTurn, InterviewSession.id)
            .join(InterviewSession, SessionTurn.session_id == InterviewSession.id)
            .where(
                InterviewSession.user_id == user_id,
                SessionTurn.answer.is_not(None),
            )
            .order_by(InterviewSession.created_at.asc(), SessionTurn.turn_index.asc())
        )
    ).all()
    turns: list = []
    session_ids: list = []
    seen: set[str] = set()
    for turn, sid in rows:
        # Exclude unanswered already; also skip empty whitespace answers.
        if not str(getattr(turn, "answer", "") or "").strip():
            continue
        turns.append(turn)
        key = str(sid)
        if key not in seen:
            seen.add(key)
            session_ids.append(sid)
    return turns, session_ids


def _merge_project_defense_from_reports(reports: list[dict]) -> dict:
    projects: list[str] = []
    demonstrated: list[str] = []
    gaps: list[str] = []
    ownership: list[str] = []
    for content in reports:
        diag = content.get("diagnostics") if isinstance(content, dict) else None
        if not isinstance(diag, dict):
            continue
        pd = diag.get("project_defense")
        if not isinstance(pd, dict) or not pd.get("has_data"):
            continue
        for p in pd.get("projects_assessed") or []:
            if p and p not in projects:
                projects.append(str(p)[:80])
        for d in pd.get("demonstrated") or []:
            if d and d not in demonstrated:
                demonstrated.append(str(d)[:120])
        for g in pd.get("knowledge_gaps") or []:
            if g and g not in gaps:
                gaps.append(str(g)[:120])
        for o in pd.get("ownership_unclear") or []:
            if o and o not in ownership:
                ownership.append(str(o)[:80])
    # Also derive from turns if reports lack nested block — handled by caller.
    return {
        "projects_assessed": projects[:8],
        "demonstrated": demonstrated[:8],
        "knowledge_gaps": gaps[:8],
        "ownership_unclear": ownership[:6],
        "has_data": bool(projects or demonstrated or gaps or ownership),
    }


def _adaptive_samples_from_reports(reports: list[dict]) -> list[dict]:
    samples: list[dict] = []
    for content in reports:
        if not isinstance(content, dict):
            continue
        diag = content.get("diagnostics") if isinstance(content.get("diagnostics"), dict) else {}
        # knowledge_state may live on turn details; surface weak concepts from diagnostics.
        for row in list(diag.get("identified_weaknesses") or [])[:2]:
            if isinstance(row, dict) and row.get("concept"):
                samples.append(
                    {
                        "concept": row["concept"],
                        "status": row.get("status"),
                        "source": "diagnostics",
                    }
                )
        for row in list(diag.get("strengths") or [])[:1]:
            if isinstance(row, dict) and row.get("concept"):
                samples.append(
                    {
                        "concept": row["concept"],
                        "status": "mastered",
                        "source": "diagnostics",
                    }
                )
        if len(samples) >= 5:
            break
    return samples[:5]


async def get_career_intelligence_for_user(
    db: AsyncSession,
    user_id,
    *,
    mongo_db: object | None = None,
    claim_seeds: list[dict] | None = None,
) -> dict:
    """Load stored evidence and compose career intelligence (no LLM).

    Loads the Shared Candidate Intelligence Snapshot when possible so overview,
    projects, claims, and track-scoped gaps stay consistent with onboarding review.
    Interview-turn aggregates remain the source of demonstrated strengths/weaknesses.
    """
    from app.models.feedback import FeedbackReport
    from app.services.feedback_service import overall_score_from_content

    snapshot = None
    try:
        from app.services.candidate_intelligence import get_candidate_intelligence_for_user

        snapshot = await get_candidate_intelligence_for_user(
            db, user_id, mongo_db=mongo_db
        )
    except Exception:  # noqa: BLE001 — career intel must still work without snapshot
        snapshot = None

    report_rows = (
        await db.execute(
            select(FeedbackReport, Track, InterviewSession)
            .join(Track, Track.id == FeedbackReport.track_id)
            .join(InterviewSession, InterviewSession.id == FeedbackReport.session_id)
            .where(FeedbackReport.user_id == user_id)
            .order_by(FeedbackReport.created_at.asc())
        )
    ).all()

    assessment_rows: list[dict] = []
    report_contents: list[dict] = []
    for report, track, session in report_rows:
        content = report.content if isinstance(report.content, dict) else {}
        report_contents.append(content)
        assessment_rows.append(
            {
                "session_id": str(report.session_id),
                "track_id": str(report.track_id),
                "track_subject": track.subject,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "overall_score": overall_score_from_content(content),
                "questions_attempted": len(content.get("question_assessments") or []),
                "track_archived": track.archived_at is not None,
            }
        )

    turns, session_ids = await _user_answered_turns(db, user_id)
    concept_summary = weakness_service.aggregate_turns(turns, session_order=session_ids)

    # Project defense: prefer report diagnostics; fall back to turn meta scan.
    project_defense = _merge_project_defense_from_reports(report_contents)
    if not project_defense.get("has_data"):
        project_defense = probe_service.project_defense_findings(turns)

    # Planned topics from active track briefs (for not-yet-assessed).
    tracks = (
        await db.execute(
            select(Track).where(Track.user_id == user_id, Track.archived_at.is_(None))
        )
    ).scalars().all()
    focus_track_id = str(tracks[0].id) if tracks else None
    planned: list[str] = []
    domain_profile = None
    for track in tracks[:6]:
        brief = (
            await db.execute(
                select(InterviewBrief)
                .where(InterviewBrief.track_id == track.id)
                .order_by(InterviewBrief.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if brief is None or not isinstance(brief.content, dict):
            continue
        content = brief.content
        if domain_profile is None and isinstance(content.get("domain_profile"), dict):
            domain_profile = content.get("domain_profile")
        for qa in content.get("question_areas") or []:
            if isinstance(qa, dict) and qa.get("topic"):
                planned.append(str(qa["topic"]))
        for comp in content.get("competencies") or []:
            if isinstance(comp, dict) and comp.get("name"):
                planned.append(str(comp["name"]))
            elif isinstance(comp, str):
                planned.append(comp)

    # Prefer preparation goals from the shared snapshot when present.
    prefs = None
    if isinstance(snapshot, dict):
        goals = (snapshot.get("profile") or {}).get("career_goals")
        if isinstance(goals, dict) and (
            goals.get("interests") or goals.get("target_role") or goals.get("confirmed")
        ):
            prefs = {
                "interests": list(goals.get("interests") or []),
                "target_role": goals.get("target_role"),
                "technical_areas": list(goals.get("technical_areas") or []),
                "focus_skills": list(goals.get("focus_skills") or []),
                "focus_projects": list(goals.get("focus_projects") or []),
                "placement_target": goals.get("placement_target"),
                "experience_level": goals.get("experience_level"),
                "behavioral_goals": goals.get("behavioral_goals"),
                "confirmed": bool(goals.get("confirmed")),
            }
    if prefs is None and mongo_db is not None:
        try:
            from app.services import conversation_store

            prefs = await conversation_store.get_preparation_preferences(
                mongo_db, str(user_id)
            )
        except Exception:
            prefs = None

    has_projects = bool(isinstance(snapshot, dict) and snapshot.get("projects"))
    if not has_projects:
        try:
            from app.services.vault_service import list_items

            items = await list_items(db, user_id)
            has_projects = any(
                (getattr(i, "category", None) or "").lower() == "project" for i in items
            )
        except Exception:
            has_projects = False

    seeds = list(claim_seeds or [])

    return compose_career_intelligence(
        concept_summary=concept_summary,
        assessment_rows=assessment_rows,
        planned_topics=_dedupe_preserve(planned, limit=40),
        project_defense_aggregate=project_defense,
        prefs=prefs if isinstance(prefs, dict) else None,
        domain_profile=domain_profile if isinstance(domain_profile, dict) else None,
        claim_seeds=seeds,
        focus_track_id=focus_track_id,
        has_projects=has_projects,
        adaptive_knowledge_samples=_adaptive_samples_from_reports(report_contents),
        candidate_intelligence=snapshot,
    )
