"""Shared Candidate Intelligence Composer (Step 0).

Deterministic, read-only composition of vault + onboarding prefs/review +
interview turns + feedback reports into one CandidateIntelligenceSnapshot.

Does not invent skills, scores, or experience. Does not write to any store.
Also exposes ``build_interview_prep_context`` for start_session / brief authoring
(Step 3) — never auto-picks an arbitrary primary project.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import career_intelligence as career_intel
from app.services import probe as probe_service
from app.services import weakness as weakness_service
from app.services.preparation_goals import (
    EMPTY_PREFERENCES,
    infer_candidate_background,
    normalize_preferences,
)
from app.services.vault_service import missing_project_details

_SNAPSHOT_VERSION = 1
_MAX_PROJECTS = 12
_MAX_CLAIMS = 40
_MAX_REPORTS = 12
_MAX_TRACKS = 20
_MAX_TOPICS_PER_TRACK = 24

_PROJECT_DETAIL_ALIASES: dict[str, tuple[str, ...]] = {
    "description": ("purpose", "description"),
    "technologies": ("technologies", "stack", "tools"),
    "contribution": ("contribution", "role"),
    "architecture": ("architecture",),
    "challenges": ("challenges", "challenge"),
    "outcomes": ("outcome", "outcomes"),
}


def empty_candidate_intelligence_snapshot(
    *,
    reason: str | None = None,
    sources_available: dict[str, bool] | None = None,
) -> dict:
    """Valid empty snapshot when the candidate has no data yet."""
    return compose_candidate_intelligence(
        user_profile=None,
        vault_items=[],
        preferences=None,
        profile_review=None,
        coach_context=None,
        tracks=[],
        turn_rows=[],
        report_rows=[],
        progression_by_track={},
        sources_available=sources_available
        or {
            "vault": True,
            "onboarding": True,
            "turns": True,
            "feedback": True,
            "user_profile": True,
        },
        composition_notes=[reason] if reason else ["No candidate evidence available yet."],
    )


def compose_candidate_intelligence(
    *,
    user_profile: dict | None,
    vault_items: list[dict],
    preferences: dict | None,
    profile_review: dict | None,
    coach_context: dict | None,
    tracks: list[dict],
    turn_rows: list[dict],
    report_rows: list[dict],
    progression_by_track: dict[str, dict] | None = None,
    sources_available: dict[str, bool] | None = None,
    composition_notes: list[str] | None = None,
    composed_at: str | None = None,
) -> dict:
    """Pure composer — safe for unit tests without DB/Mongo.

    Inputs are already-normalized plain dicts (never ORM objects).
    """
    notes = list(composition_notes or [])
    prefs = normalize_preferences(preferences) if preferences is not None else dict(
        EMPTY_PREFERENCES
    )
    if not prefs.get("target_role"):
        notes.append(
            "Target role not confirmed — readiness and interviews stay domain-neutral "
            "until the candidate chooses a role."
        )
    vault = [row for row in vault_items if isinstance(row, dict)]
    profile = _compose_profile(
        user_profile=user_profile if isinstance(user_profile, dict) else None,
        vault_items=vault,
        preferences=prefs,
        notes=notes,
    )
    projects = _compose_projects(vault)
    evidence = _compose_knowledge_evidence(
        vault_items=vault,
        turn_rows=turn_rows,
        tracks=tracks,
        notes=notes,
    )
    history = _compose_interview_history(
        tracks=tracks,
        turn_rows=turn_rows,
        report_rows=report_rows,
        progression_by_track=progression_by_track or {},
        evidence=evidence,
    )
    prep = _compose_preparation_preferences(prefs, profile_review)
    feedback = _compose_feedback_history(report_rows)

    available = {
        "vault": True,
        "onboarding": True,
        "turns": True,
        "feedback": True,
        "user_profile": user_profile is not None,
        **(sources_available or {}),
    }

    return {
        "snapshot_version": _SNAPSHOT_VERSION,
        "composed_at": composed_at or _now_iso(),
        "sources_available": available,
        "composition_notes": _dedupe_notes(notes),
        "profile": profile,
        "projects": projects,
        "knowledge_evidence": evidence,
        "interview_history": history,
        "preparation_preferences": prep,
        "feedback_history": feedback,
        "provenance_policy": {
            "claims_are_not_proof": True,
            "unknown_is_not_weak": True,
            "turns_are_planning_truth": True,
            "reports_are_secondary_digest": True,
            "track_scope_preserved": True,
            "user_profile_vs_vault": (
                "Both retained under profile.user_profile and profile.vault; "
                "conflicts listed in profile.source_conflicts without overwrite."
            ),
        },
    }


async def get_candidate_intelligence_for_user(
    db: AsyncSession,
    user_id,
    *,
    mongo_db: object | None = None,
    user: Any | None = None,
) -> dict:
    """Load stores gracefully and compose a snapshot. Never raises for empty sources."""
    notes: list[str] = []
    available = {
        "vault": False,
        "onboarding": False,
        "turns": False,
        "feedback": False,
        "user_profile": False,
    }

    user_profile = None
    try:
        user_profile = await _load_user_profile(db, user_id, user=user)
        available["user_profile"] = user_profile is not None
    except Exception as exc:  # noqa: BLE001 — partial snapshot on source failure
        notes.append(f"user_profile unavailable: {type(exc).__name__}")

    vault_items: list[dict] = []
    try:
        from app.services.vault_service import list_items, _item_summary

        rows = await list_items(db, user_id)
        vault_items = [_item_summary(i) for i in rows]
        available["vault"] = True
    except Exception as exc:  # noqa: BLE001
        notes.append(f"vault unavailable: {type(exc).__name__}")

    preferences = None
    profile_review = None
    coach_context = None
    if mongo_db is not None:
        try:
            from app.services import conversation_store

            uid = str(user_id)
            preferences = await conversation_store.get_preparation_preferences(
                mongo_db, uid
            )
            profile_review = await conversation_store.get_profile_review(mongo_db, uid)
            coach_context = await conversation_store.get_coach_context(mongo_db, uid)
            available["onboarding"] = True
        except Exception as exc:  # noqa: BLE001
            notes.append(f"onboarding unavailable: {type(exc).__name__}")
    else:
        notes.append("onboarding skipped: no mongo_db provided")

    tracks: list[dict] = []
    try:
        tracks = await _load_tracks(db, user_id)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"tracks unavailable: {type(exc).__name__}")

    turn_rows: list[dict] = []
    try:
        turn_rows = await _load_turn_rows(db, user_id)
        available["turns"] = True
    except Exception as exc:  # noqa: BLE001
        notes.append(f"turns unavailable: {type(exc).__name__}")

    report_rows: list[dict] = []
    try:
        report_rows = await _load_report_rows(db, user_id)
        available["feedback"] = True
    except Exception as exc:  # noqa: BLE001
        notes.append(f"feedback unavailable: {type(exc).__name__}")

    progression: dict[str, dict] = {}
    try:
        progression = await _load_progression(db, [t["track_id"] for t in tracks])
    except Exception as exc:  # noqa: BLE001
        notes.append(f"progression unavailable: {type(exc).__name__}")

    return compose_candidate_intelligence(
        user_profile=user_profile,
        vault_items=vault_items,
        preferences=preferences,
        profile_review=profile_review,
        coach_context=coach_context,
        tracks=tracks,
        turn_rows=turn_rows,
        report_rows=report_rows,
        progression_by_track=progression,
        sources_available=available,
        composition_notes=notes,
    )


# ---------------------------------------------------------------------------
# Section composers
# ---------------------------------------------------------------------------


def _compose_profile(
    *,
    user_profile: dict | None,
    vault_items: list[dict],
    preferences: dict,
    notes: list[str],
) -> dict:
    vault_by_cat: dict[str, list[dict]] = defaultdict(list)
    for item in vault_items:
        cat = str(item.get("category") or "other").lower()
        vault_by_cat[cat].append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "details": dict(item.get("details") or {}),
                "source": item.get("source"),
                "evidence_kind": "claim",
            }
        )

    background = infer_candidate_background(vault_items)
    conflicts = _profile_conflicts(user_profile, vault_by_cat, notes)

    return {
        "user_profile": {
            "professional_title": (user_profile or {}).get("professional_title"),
            "introduction": (user_profile or {}).get("introduction"),
            "skills": list((user_profile or {}).get("skills") or []),
            "education": (user_profile or {}).get("education"),
            "onboarding_completed_at": (user_profile or {}).get("onboarding_completed_at"),
            "source": "users_table",
        },
        "vault": {
            "education": vault_by_cat.get("education", [])[:_MAX_CLAIMS],
            "skills": vault_by_cat.get("skill", [])[:_MAX_CLAIMS],
            "internships": vault_by_cat.get("internship", [])[:_MAX_CLAIMS],
            "achievements": vault_by_cat.get("achievement", [])[:_MAX_CLAIMS],
            "projects": [
                {"id": p.get("id"), "title": p.get("title"), "source": p.get("source")}
                for p in vault_by_cat.get("project", [])[:_MAX_PROJECTS]
            ],
            "other": vault_by_cat.get("other", [])[:12],
            "source": "vault_items",
        },
        "career_goals": {
            "interests": list(preferences.get("interests") or []),
            "target_role": preferences.get("target_role"),
            "placement_target": preferences.get("placement_target"),
            "technical_areas": list(preferences.get("technical_areas") or []),
            "focus_skills": list(preferences.get("focus_skills") or []),
            "focus_projects": list(preferences.get("focus_projects") or []),
            "experience_level": preferences.get("experience_level"),
            "behavioral_goals": preferences.get("behavioral_goals"),
            "confirmed": bool(preferences.get("confirmed")),
            "source": "preparation_preferences",
            "evidence_kind": "preference",
        },
        "inferred_background": {
            **background,
            "source": "computed_from_vault",
            "evidence_kind": "derived_claim",
            "note": "Heuristic from vault text only — not interview proof.",
        },
        "source_conflicts": conflicts,
    }


def _compose_projects(vault_items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in vault_items:
        if str(item.get("category") or "").lower() != "project":
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        known = probe_service.project_known_fields(details)
        # Also surface alias groups for the snapshot contract.
        fields = {
            label: _first_detail(details, keys)
            for label, keys in _PROJECT_DETAIL_ALIASES.items()
        }
        missing = probe_service.project_missing_fields(details)
        # Keep vault_service completeness keys too (never invent).
        for key in missing_project_details(details):
            if key not in missing:
                missing.append(key)
        out.append(
            {
                "name": item.get("title"),
                "id": item.get("id"),
                "vault_source": item.get("source"),
                "evidence_kind": "claim",
                "description": fields.get("description"),
                "technologies": fields.get("technologies"),
                "contribution": fields.get("contribution"),
                "architecture": fields.get("architecture"),
                "challenges": fields.get("challenges"),
                "outcomes": fields.get("outcomes"),
                "known_fields": known,
                "needs_clarification": missing,
                "raw_details_keys": sorted(str(k) for k in details.keys()),
            }
        )
        if len(out) >= _MAX_PROJECTS:
            break
    return out


def _compose_knowledge_evidence(
    *,
    vault_items: list[dict],
    turn_rows: list[dict],
    tracks: list[dict],
    notes: list[str],
) -> dict:
    claims = _claim_skills_and_topics(vault_items)

    # Global demonstrated evidence from turns (cross-track digest — labeled).
    global_turns = [_turn_ns(row) for row in turn_rows]
    global_order = _session_order(turn_rows)
    global_summary = weakness_service.aggregate_turns(
        global_turns, session_order=global_order
    )
    global_intel = career_intel.build_concept_intelligence(global_summary)

    # Per-track demonstrated evidence — never silently fold into other tracks.
    by_track: dict[str, list[dict]] = defaultdict(list)
    for row in turn_rows:
        tid = str(row.get("track_id") or "")
        if tid:
            by_track[tid].append(row)

    track_evidence: list[dict] = []
    track_meta = {str(t.get("track_id")): t for t in tracks if t.get("track_id")}
    for tid, rows in by_track.items():
        summary = weakness_service.aggregate_turns(
            [_turn_ns(r) for r in rows],
            session_order=_session_order(rows),
        )
        intel = career_intel.build_concept_intelligence(summary)
        meta = track_meta.get(tid) or {}
        assessed = {
            str(c.get("concept") or "")
            for c in (summary.get("concepts") or [])
            if isinstance(c, dict) and c.get("concept")
        }
        planned = list(meta.get("planned_topics") or [])
        not_assessed = career_intel.build_not_yet_assessed(planned, assessed)
        track_evidence.append(
            {
                "track_id": tid,
                "track_subject": meta.get("subject"),
                "scope": "track",
                "demonstrated_strengths": intel["demonstrated_strengths"],
                "demonstrated_weaknesses": intel["demonstrated_weaknesses"],
                "developing": intel["developing"],
                "insufficient_evidence": intel["insufficient_evidence"],
                "not_assessed": not_assessed,
                "concepts": list(summary.get("concepts") or [])[:_MAX_TOPICS_PER_TRACK],
                "has_data": bool(summary.get("has_data")),
            }
        )

    # Tracks with a brief but no answered turns → all planned topics not_assessed.
    seen_tracks = {row["track_id"] for row in track_evidence}
    for meta in tracks:
        tid = str(meta.get("track_id") or "")
        if not tid or tid in seen_tracks:
            continue
        planned = list(meta.get("planned_topics") or [])
        if not planned:
            continue
        track_evidence.append(
            {
                "track_id": tid,
                "track_subject": meta.get("subject"),
                "scope": "track",
                "demonstrated_strengths": [],
                "demonstrated_weaknesses": [],
                "developing": [],
                "insufficient_evidence": [],
                "not_assessed": planned[:12],
                "concepts": [],
                "has_data": False,
            }
        )

    if not turn_rows and not claims["skills"] and not claims["topics"]:
        notes.append("No claim or interview evidence yet — knowledge sections empty.")

    all_planned = []
    for t in tracks:
        all_planned.extend(t.get("planned_topics") or [])
    assessed_global = {
        str(c.get("concept") or "")
        for c in (global_summary.get("concepts") or [])
        if isinstance(c, dict) and c.get("concept")
    }
    cross_not_assessed = career_intel.build_not_yet_assessed(all_planned, assessed_global)

    return {
        "candidate_claims": {
            "evidence_kind": "claim",
            "skills": claims["skills"],
            "topics": claims["topics"],
            "note": (
                "From resume/vault/onboarding only. A listed skill is not "
                "demonstrated interview ability."
            ),
        },
        "interview_demonstrated": {
            "evidence_kind": "demonstrated",
            "scope": "cross_track_digest",
            "note": (
                "Aggregated from answered turns across tracks for overview only. "
                "Use by_track for planning within a track."
            ),
            "strengths": global_intel["demonstrated_strengths"],
            "weaknesses": global_intel["demonstrated_weaknesses"],
            "developing": global_intel["developing"],
            "insufficient_evidence": global_intel["insufficient_evidence"],
            "has_data": bool(global_summary.get("has_data")),
        },
        "not_assessed": {
            "evidence_kind": "not_assessed",
            "note": "Unknown is not weak — topics planned or claimed but not answered in interviews.",
            "from_briefs_cross_track": cross_not_assessed,
            "claimed_skills_without_interview": _claims_without_demo(
                claims["skills"], assessed_global
            ),
        },
        "by_track": track_evidence[:_MAX_TRACKS],
    }


def _compose_interview_history(
    *,
    tracks: list[dict],
    turn_rows: list[dict],
    report_rows: list[dict],
    progression_by_track: dict[str, dict],
    evidence: dict,
) -> dict:
    topics_by_track: dict[str, list[str]] = defaultdict(list)
    for row in turn_rows:
        tid = str(row.get("track_id") or "")
        area = str(row.get("question_area") or "").strip()
        if tid and area and area not in topics_by_track[tid]:
            topics_by_track[tid].append(area[:80])

    reports_by_track: dict[str, list[dict]] = defaultdict(list)
    for rep in report_rows:
        tid = str(rep.get("track_id") or "")
        if tid:
            reports_by_track[tid].append(rep)

    evidence_by_track = {
        str(row.get("track_id")): row
        for row in (evidence.get("by_track") or [])
        if row.get("track_id")
    }

    track_histories: list[dict] = []
    for meta in tracks[:_MAX_TRACKS]:
        tid = str(meta.get("track_id") or "")
        if not tid:
            continue
        ev = evidence_by_track.get(tid) or {}
        prog = progression_by_track.get(tid) or {}
        track_reports = reports_by_track.get(tid) or []
        latest = track_reports[-1] if track_reports else None
        track_histories.append(
            {
                "track_id": tid,
                "track_subject": meta.get("subject"),
                "archived": bool(meta.get("archived")),
                "topics_covered": topics_by_track.get(tid, [])[:_MAX_TOPICS_PER_TRACK],
                "demonstrated_strengths": [
                    r.get("concept")
                    for r in (ev.get("demonstrated_strengths") or [])
                    if r.get("concept")
                ][:8],
                "repeated_difficulties": [
                    r.get("concept")
                    for r in (ev.get("demonstrated_weaknesses") or [])
                    if r.get("concept") and int(r.get("times_asked") or 0) >= 2
                ][:8],
                "previously_assessed_concepts": [
                    c.get("concept")
                    for c in (ev.get("concepts") or [])
                    if isinstance(c, dict) and c.get("concept")
                ][:_MAX_TOPICS_PER_TRACK],
                "not_assessed": list(ev.get("not_assessed") or [])[:12],
                "feedback_summary": _report_digest(latest) if latest else None,
                "report_count": len(track_reports),
                "progression": {
                    "strict_completed": prog.get("strict_completed", 0),
                    "guided_state": prog.get("guided_state", "LOCKED"),
                },
                "scope": "track",
            }
        )

    # Cross-track overview with explicit origin label.
    cross = evidence.get("interview_demonstrated") or {}
    return {
        "tracks": track_histories,
        "cross_track_overview": {
            "scope": "cross_track_digest",
            "origin": "answered_turns_across_tracks",
            "demonstrated_strengths": [
                r.get("concept") for r in (cross.get("strengths") or []) if r.get("concept")
            ][:10],
            "repeated_difficulties": [
                r.get("concept")
                for r in (cross.get("weaknesses") or [])
                if r.get("concept") and int(r.get("times_asked") or 0) >= 2
            ][:10],
            "note": (
                "Overview only — do not treat a weakness here as applying to every track."
            ),
        },
    }


def _compose_preparation_preferences(
    preferences: dict, profile_review: dict | None
) -> dict:
    review = profile_review if isinstance(profile_review, dict) else {}
    next_action = review.get("next_action") if isinstance(review.get("next_action"), dict) else None
    return {
        "goals": {
            "interests": list(preferences.get("interests") or []),
            "target_role": preferences.get("target_role"),
            "technical_areas": list(preferences.get("technical_areas") or []),
            "focus_skills": list(preferences.get("focus_skills") or []),
            "focus_projects": list(preferences.get("focus_projects") or []),
            "project_aspects": list(preferences.get("project_aspects") or []),
            "placement_target": preferences.get("placement_target"),
            "experience_level": preferences.get("experience_level"),
            "behavioral_goals": preferences.get("behavioral_goals"),
            "confirmed": bool(preferences.get("confirmed")),
        },
        "behavioral_interview_preference": bool(
            "behavioral" in (preferences.get("interests") or [])
            or preferences.get("behavioral_goals")
        ),
        # Session start options are not persisted on preferences today.
        "preferred_mode": None,
        "preferred_duration_minutes": None,
        "target_difficulty": None,
        "session_options_note": (
            "Strict/Guided mode, duration, and difficulty are chosen per session "
            "in StartInterviewModal and are not stored on preparation_preferences."
        ),
        "profile_review_next_action": next_action,
        "evidence_kind": "preference",
        "distinguish_from_ability": (
            "Preferences describe what the candidate wants to practise — "
            "not what they have demonstrated."
        ),
    }


def _compose_feedback_history(report_rows: list[dict]) -> dict:
    digests: list[dict] = []
    seen_session: set[str] = set()
    # Newest first for freshness; skip duplicate session_id.
    ordered = sorted(
        report_rows,
        key=lambda r: str(r.get("created_at") or ""),
        reverse=True,
    )
    for rep in ordered:
        sid = str(rep.get("session_id") or "")
        if sid and sid in seen_session:
            continue
        if sid:
            seen_session.add(sid)
        digests.append(_report_digest(rep))
        if len(digests) >= _MAX_REPORTS:
            break

    return {
        "reports": digests,
        "freshness_note": (
            "created_at is included per report. Older reports are historical; "
            "prefer recent reports and live turn aggregates for current evidence."
        ),
        "dedupe_rule": "At most one digest per session_id (newest kept).",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_notes(notes: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in notes:
        text = " ".join(str(raw or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:240])
        if len(out) >= 20:
            break
    return out


def _first_detail(details: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        text = " ".join(str(details.get(key) or "").split()).strip()
        if text:
            return text[:400]
    return None


def _profile_conflicts(
    user_profile: dict | None,
    vault_by_cat: dict[str, list[dict]],
    notes: list[str],
) -> list[dict]:
    conflicts: list[dict] = []
    if not user_profile:
        return conflicts

    user_skills = [
        " ".join(str(s).split()).strip()
        for s in (user_profile.get("skills") or [])
        if str(s).strip()
    ]
    vault_skills = [
        " ".join(str(i.get("title") or "").split()).strip()
        for i in vault_by_cat.get("skill", [])
        if i.get("title")
    ]
    user_norm = {s.lower() for s in user_skills}
    vault_norm = {s.lower() for s in vault_skills}
    only_user = sorted(user_norm - vault_norm)
    only_vault = sorted(vault_norm - user_norm)
    if only_user or only_vault:
        conflicts.append(
            {
                "field": "skills",
                "resolution": "retain_both",
                "user_profile_only": [s for s in user_skills if s.lower() in only_user][:12],
                "vault_only": [s for s in vault_skills if s.lower() in only_vault][:12],
                "note": "Neither source overwrites the other.",
            }
        )

    user_edu = " ".join(str(user_profile.get("education") or "").split()).strip()
    vault_edu = [
        " ".join(str(i.get("title") or "").split()).strip()
        for i in vault_by_cat.get("education", [])
        if i.get("title")
    ]
    if user_edu and vault_edu:
        if user_edu.lower() not in {v.lower() for v in vault_edu}:
            conflicts.append(
                {
                    "field": "education",
                    "resolution": "retain_both",
                    "user_profile": user_edu[:200],
                    "vault": vault_edu[:6],
                    "note": "Education strings differ; both retained.",
                }
            )
            notes.append("education conflict between users table and vault — both retained")
    return conflicts


def _claim_skills_and_topics(vault_items: list[dict]) -> dict:
    skills: list[dict] = []
    topics: list[dict] = []
    for item in vault_items:
        cat = str(item.get("category") or "").lower()
        title = " ".join(str(item.get("title") or "").split()).strip()
        if not title:
            continue
        entry = {
            "title": title[:120],
            "category": cat,
            "source": item.get("source"),
            "id": item.get("id"),
            "evidence_kind": "claim",
        }
        if cat == "skill":
            skills.append(entry)
        elif cat in ("project", "internship", "achievement", "education"):
            topics.append(entry)
        if len(skills) >= _MAX_CLAIMS and len(topics) >= _MAX_CLAIMS:
            break
    return {"skills": skills[:_MAX_CLAIMS], "topics": topics[:_MAX_CLAIMS]}


def _claims_without_demo(claim_skills: list[dict], assessed: set[str]) -> list[str]:
    assessed_norm = {weakness_service.normalize_concept(a) for a in assessed if a}
    out: list[str] = []
    for row in claim_skills:
        title = str(row.get("title") or "")
        key = weakness_service.normalize_concept(title)
        if not key:
            continue
        if key in assessed_norm or any(
            key in a or a in key for a in assessed_norm if len(a) >= 4
        ):
            continue
        out.append(title[:80])
        if len(out) >= 12:
            break
    return out


def _turn_ns(row: dict) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        question_area=row.get("question_area"),
        answer=row.get("answer"),
        evaluation_coverage=row.get("evaluation_coverage"),
        evaluation_gaps=row.get("evaluation_gaps") or [],
        session_id=row.get("session_id"),
        turn_index=row.get("turn_index") or 0,
        evaluation_detail=row.get("evaluation_detail") or {},
    )


def _session_order(turn_rows: list[dict]) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for row in turn_rows:
        sid = str(row.get("session_id") or "")
        if sid and sid not in seen:
            seen.add(sid)
            order.append(sid)
    return order


def _report_digest(rep: dict) -> dict:
    content = rep.get("content") if isinstance(rep.get("content"), dict) else {}
    created = rep.get("created_at")
    strengths = [str(x)[:160] for x in (content.get("strengths") or []) if x][:6]
    improvements = [
        str(x)[:160] for x in (content.get("improvement_areas") or []) if x
    ][:6]
    recommendations = [
        str(x)[:160] for x in (content.get("recommendations") or []) if x
    ][:6]
    comps = []
    for row in content.get("competency_assessments") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("competency_name") or "").strip()
        if not name:
            continue
        comps.append(
            {
                "competency_name": name[:120],
                "level": row.get("level"),
                "status": row.get("status"),
            }
        )
        if len(comps) >= 10:
            break
    return {
        "session_id": rep.get("session_id"),
        "track_id": rep.get("track_id"),
        "track_subject": rep.get("track_subject"),
        "created_at": created,
        "summary_overview": str(content.get("summary_overview") or "")[:500] or None,
        "strengths": strengths,
        "improvement_areas": improvements,
        "recommendations": recommendations,
        "competency_assessments": comps,
        "unassessed_topics": [
            str(x)[:80] for x in (content.get("unassessed_topics") or []) if x
        ][:8],
        "evidence_kind": "feedback_report",
        "freshness": {
            "created_at": created,
            "note": "Historical digest — confirm against recent turns before treating as current.",
        },
    }


async def _load_user_profile(
    db: AsyncSession, user_id, *, user: Any | None = None
) -> dict | None:
    row = user
    if row is None:
        from app.models.user import User

        row = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
    if row is None:
        return None
    completed = getattr(row, "onboarding_completed_at", None)
    return {
        "professional_title": getattr(row, "professional_title", None),
        "introduction": getattr(row, "introduction", None),
        "skills": list(getattr(row, "skills", None) or []),
        "education": getattr(row, "education", None),
        "onboarding_completed_at": completed.isoformat() if completed else None,
    }


async def _load_tracks(db: AsyncSession, user_id) -> list[dict]:
    from app.models.track import InterviewBrief, Track

    tracks = (
        await db.execute(
            select(Track)
            .where(Track.user_id == user_id)
            .order_by(Track.created_at.asc())
            .limit(_MAX_TRACKS)
        )
    ).scalars().all()
    out: list[dict] = []
    for track in tracks:
        brief = (
            await db.execute(
                select(InterviewBrief)
                .where(InterviewBrief.track_id == track.id)
                .order_by(InterviewBrief.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        planned: list[str] = []
        content = brief.content if brief is not None and isinstance(brief.content, dict) else {}
        for qa in content.get("question_areas") or []:
            if isinstance(qa, dict) and qa.get("topic"):
                planned.append(str(qa["topic"])[:80])
        for comp in content.get("competencies") or []:
            if isinstance(comp, dict) and comp.get("name"):
                planned.append(str(comp["name"])[:80])
            elif isinstance(comp, str) and comp.strip():
                planned.append(comp.strip()[:80])
        # Dedupe planned topics preserving order.
        seen: set[str] = set()
        unique_planned: list[str] = []
        for topic in planned:
            key = topic.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_planned.append(topic)
        out.append(
            {
                "track_id": str(track.id),
                "subject": track.subject,
                "archived": track.archived_at is not None,
                "planned_topics": unique_planned[:40],
            }
        )
    return out


async def _load_turn_rows(db: AsyncSession, user_id) -> list[dict]:
    from app.models.interview import InterviewSession, SessionTurn

    rows = (
        await db.execute(
            select(SessionTurn, InterviewSession)
            .join(InterviewSession, SessionTurn.session_id == InterviewSession.id)
            .where(
                InterviewSession.user_id == user_id,
                SessionTurn.answer.is_not(None),
            )
            .order_by(InterviewSession.created_at.asc(), SessionTurn.turn_index.asc())
        )
    ).all()
    out: list[dict] = []
    for turn, session in rows:
        answer = str(getattr(turn, "answer", "") or "").strip()
        if not answer:
            continue
        out.append(
            {
                "session_id": str(session.id),
                "track_id": str(session.track_id),
                "turn_index": int(turn.turn_index or 0),
                "question_area": turn.question_area,
                "answer": answer,
                "evaluation_coverage": turn.evaluation_coverage,
                "evaluation_gaps": list(turn.evaluation_gaps or []),
                "evaluation_detail": turn.evaluation_detail
                if isinstance(turn.evaluation_detail, dict)
                else {},
                "created_at": turn.created_at.isoformat()
                if getattr(turn, "created_at", None)
                else None,
            }
        )
    return out


async def _load_report_rows(db: AsyncSession, user_id) -> list[dict]:
    from app.models.feedback import FeedbackReport
    from app.models.track import Track

    rows = (
        await db.execute(
            select(FeedbackReport, Track)
            .join(Track, Track.id == FeedbackReport.track_id)
            .where(FeedbackReport.user_id == user_id)
            .order_by(FeedbackReport.created_at.asc())
        )
    ).all()
    out: list[dict] = []
    for report, track in rows:
        content = report.content if isinstance(report.content, dict) else {}
        out.append(
            {
                "session_id": str(report.session_id),
                "track_id": str(report.track_id),
                "track_subject": track.subject,
                "track_archived": track.archived_at is not None,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "content": content,
            }
        )
    return out


async def _load_progression(db: AsyncSession, track_ids: list[str]) -> dict[str, dict]:
    if not track_ids:
        return {}
    from uuid import UUID

    from app.models.feedback import ProgressionState

    uuids = []
    for tid in track_ids:
        try:
            uuids.append(UUID(str(tid)))
        except (TypeError, ValueError):
            continue
    if not uuids:
        return {}
    rows = (
        await db.execute(
            select(ProgressionState).where(ProgressionState.track_id.in_(uuids))
        )
    ).scalars().all()
    return {
        str(row.track_id): {
            "strict_completed": int(row.strict_completed or 0),
            "guided_state": row.guided_state or "LOCKED",
        }
        for row in rows
    }


# ---------------------------------------------------------------------------
# Step 3 — interview preparation context (start_session / brief authoring)
# ---------------------------------------------------------------------------


def _norm_title(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def resolve_selected_project_titles(
    snapshot: dict | None,
    *,
    claim_seeds: list | None = None,
    explicit_projects: list[str] | None = None,
) -> list[str]:
    """Return only explicitly selected project titles that exist in the vault.

    Never falls back to "first vault project" or any other arbitrary pick.
    """
    wanted: list[str] = []
    seen: set[str] = set()

    def _add(raw: str | None) -> None:
        title = " ".join(str(raw or "").split()).strip()
        if not title:
            return
        key = title.lower()
        if key in seen:
            return
        seen.add(key)
        wanted.append(title[:120])

    for name in explicit_projects or []:
        _add(name)
    if isinstance(snapshot, dict):
        goals = (snapshot.get("profile") or {}).get("career_goals") or {}
        for name in goals.get("focus_projects") or []:
            _add(str(name))
        prep = (snapshot.get("preparation_preferences") or {}).get("goals") or {}
        for name in prep.get("focus_projects") or []:
            _add(str(name))
    for seed in claim_seeds or []:
        if isinstance(seed, dict):
            _add(seed.get("title"))

    if not wanted:
        return []

    vault_names: dict[str, str] = {}
    if isinstance(snapshot, dict):
        for proj in snapshot.get("projects") or []:
            if isinstance(proj, dict) and proj.get("name"):
                vault_names[_norm_title(proj.get("name"))] = str(proj["name"])[:120]
        for row in ((snapshot.get("profile") or {}).get("vault") or {}).get("projects") or []:
            if isinstance(row, dict) and row.get("title"):
                vault_names[_norm_title(row.get("title"))] = str(row["title"])[:120]

    if not vault_names:
        # No vault projects known — keep requested names only if caller has none to match.
        return wanted[:6]

    matched: list[str] = []
    for title in wanted:
        key = _norm_title(title)
        if key in vault_names:
            matched.append(vault_names[key])
            continue
        # Soft containment match against vault titles.
        hit = next(
            (
                vault_names[vkey]
                for vkey in vault_names
                if key in vkey or vkey in key
            ),
            None,
        )
        if hit and hit not in matched:
            matched.append(hit)
    return matched[:6]


def build_interview_prep_context(
    snapshot: dict | None,
    *,
    track_id: str | None = None,
    track_subject: str | None = None,
    claim_seeds: list | None = None,
    explicit_projects: list[str] | None = None,
    mode: str | None = None,
    duration_minutes: int | None = None,
) -> dict:
    """Compact, deterministic context for interview preparation.

    Distinguishes claims vs demonstrated evidence. Track-scoped learning history
    is preferred when ``track_id`` is provided — never silently imports unrelated
    track weaknesses as global weaknesses.
    """
    snap = snapshot if isinstance(snapshot, dict) else {}
    profile = snap.get("profile") or {}
    goals = profile.get("career_goals") or {}
    vault = profile.get("vault") or {}
    knowledge = snap.get("knowledge_evidence") or {}
    selected_projects = resolve_selected_project_titles(
        snap, claim_seeds=claim_seeds, explicit_projects=explicit_projects
    )

    track_block = None
    for row in knowledge.get("by_track") or []:
        if not isinstance(row, dict):
            continue
        if track_id and str(row.get("track_id") or "") == str(track_id):
            track_block = row
            break
        if (
            track_block is None
            and track_subject
            and _norm_title(row.get("track_subject")) == _norm_title(track_subject)
        ):
            track_block = row

    def _names(rows: list | None, *, limit: int = 8) -> list[str]:
        out: list[str] = []
        for item in rows or []:
            if isinstance(item, dict) and item.get("concept"):
                out.append(str(item["concept"])[:80])
            elif isinstance(item, str) and item.strip():
                out.append(item.strip()[:80])
            if len(out) >= limit:
                break
        return out

    if track_block:
        demonstrated_strengths = _names(track_block.get("demonstrated_strengths"))
        demonstrated_weaknesses = _names(track_block.get("demonstrated_weaknesses"))
        developing = _names(track_block.get("developing"))
        covered_concepts = [
            str(c.get("concept") or "")[:80]
            for c in (track_block.get("concepts") or [])
            if isinstance(c, dict) and c.get("concept")
        ][:16]
        not_assessed = list(track_block.get("not_assessed") or [])[:12]
        evidence_scope = "track"
    else:
        demo = knowledge.get("interview_demonstrated") or {}
        demonstrated_strengths = _names(demo.get("strengths"))
        demonstrated_weaknesses = _names(demo.get("weaknesses"))
        developing = _names(demo.get("developing"))
        covered_concepts = []
        not_assessed = list(
            (knowledge.get("not_assessed") or {}).get("from_briefs_cross_track") or []
        )[:12]
        evidence_scope = "cross_track_digest" if demo.get("has_data") else "none"

    selected_project_details = []
    selected_set = {_norm_title(t) for t in selected_projects}
    for proj in snap.get("projects") or []:
        if not isinstance(proj, dict) or not proj.get("name"):
            continue
        if _norm_title(proj.get("name")) not in selected_set:
            continue
        selected_project_details.append(
            {
                "name": proj.get("name"),
                "technologies": proj.get("technologies"),
                "contribution": proj.get("contribution"),
                "architecture": proj.get("architecture"),
                "outcomes": proj.get("outcomes"),
                "needs_clarification": list(proj.get("needs_clarification") or [])[:6],
                "evidence_kind": "claim",
            }
        )

    return {
        "source": "candidate_intelligence_snapshot",
        "track_id": str(track_id) if track_id else None,
        "track_subject": track_subject,
        "evidence_scope": evidence_scope,
        "background": {
            "education": [
                r.get("title")
                for r in (vault.get("education") or [])
                if isinstance(r, dict) and r.get("title")
            ][:6],
            "skills": [
                r.get("title")
                for r in (vault.get("skills") or [])
                if isinstance(r, dict) and r.get("title")
            ][:12],
            "internships": [
                r.get("title")
                for r in (vault.get("internships") or [])
                if isinstance(r, dict) and r.get("title")
            ][:6],
            "evidence_kind": "claim",
        },
        "career_goals": {
            "target_role": goals.get("target_role"),
            "interests": list(goals.get("interests") or [])[:8],
            "technical_areas": list(goals.get("technical_areas") or [])[:8],
            "focus_skills": list(goals.get("focus_skills") or [])[:8],
            "focus_projects": list(goals.get("focus_projects") or [])[:6],
            "behavioral_goals": goals.get("behavioral_goals"),
            "evidence_kind": "preference",
        },
        "selected_projects": selected_projects,
        "selected_project_details": selected_project_details,
        "project_selection_note": (
            "Only explicitly selected projects are included. "
            "No arbitrary vault project was auto-chosen as primary."
            if selected_projects
            else (
                "No project explicitly selected — interview prep will not "
                "designate a primary project from the vault."
            )
        ),
        "demonstrated_strengths": demonstrated_strengths,
        "demonstrated_weaknesses": demonstrated_weaknesses,
        "developing": developing,
        "covered_concepts": covered_concepts,
        "not_assessed": not_assessed,
        "unverified_claims": [
            str(s.get("title") or "")[:80]
            for s in ((knowledge.get("candidate_claims") or {}).get("skills") or [])
            if isinstance(s, dict) and s.get("title")
        ][:12],
        "session_preferences": {
            "mode": mode,
            "duration_minutes": duration_minutes,
            "note": (
                "Mode and duration come from the start-session request. "
                "They are preferences, not demonstrated ability."
            ),
        },
        "policy": {
            "claims_are_not_proof": True,
            "unknown_is_not_weak": True,
            "no_arbitrary_primary_project": True,
            "track_scope_preferred": bool(track_id),
        },
    }


def filter_vault_items_for_selected_projects(
    items: list,
    selected_projects: list[str] | None,
    *,
    include_non_projects: bool = True,
) -> list:
    """Filter vault ORM/dict items. Projects kept only when explicitly selected."""
    selected = {_norm_title(t) for t in (selected_projects or []) if t}
    out: list = []
    for item in items or []:
        if isinstance(item, dict):
            cat = str(item.get("category") or "").lower()
            title = str(item.get("title") or item.get("name") or "")
        else:
            cat = str(getattr(item, "category", "") or "").lower()
            title = str(getattr(item, "title", "") or "")
        if cat == "project":
            if not selected:
                continue
            key = _norm_title(title)
            if key in selected or any(key in s or s in key for s in selected if s):
                out.append(item)
            continue
        if include_non_projects:
            out.append(item)
    return out


def compact_brief_authoring_context(prep: dict | None) -> dict | None:
    """Trim prep context for track-creator LLM payload (token-safe)."""
    if not isinstance(prep, dict):
        return None
    return {
        "career_goals": prep.get("career_goals"),
        "background_skills": list((prep.get("background") or {}).get("skills") or [])[:10],
        "background_education": list((prep.get("background") or {}).get("education") or [])[:4],
        "selected_projects": list(prep.get("selected_projects") or [])[:4],
        "selected_project_details": list(prep.get("selected_project_details") or [])[:4],
        "demonstrated_strengths": list(prep.get("demonstrated_strengths") or [])[:6],
        "demonstrated_weaknesses": list(prep.get("demonstrated_weaknesses") or [])[:6],
        "covered_concepts": list(prep.get("covered_concepts") or [])[:10],
        "not_assessed": list(prep.get("not_assessed") or [])[:8],
        "project_selection_note": prep.get("project_selection_note"),
        "policy": prep.get("policy"),
        "evidence_scope": prep.get("evidence_scope"),
        "track_subject": prep.get("track_subject"),
    }
