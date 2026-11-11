"""Post-onboarding profile review, validation statuses, and preparation roadmap.

Built only from persisted vault items, preparation preferences, and optional
interview history. Never invents proficiency scores or unverified facts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.services.preparation_goals import (
    GOAL_INTEREST_LABELS,
    normalize_preferences,
    recommend_track_seeds,
    summarize_preferences,
)
from app.services.vault_service import find_near_duplicates, missing_project_details

STATUSES = ("confirmed", "needs_clarification", "not_assessed")


def vault_fingerprint(items: list) -> str:
    payload = [
        {
            "id": str(getattr(i, "id", "")),
            "category": getattr(i, "category", ""),
            "title": getattr(i, "title", ""),
            "details": getattr(i, "details", None) or {},
            "source": getattr(i, "source", ""),
        }
        for i in items
    ]
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def classify_item(
    item,
    *,
    duplicate_ids: set[str],
    assessed_subjects: set[str],
    user_override: dict | None = None,
) -> dict:
    """Return status for one vault item without inventing technical proficiency."""
    if user_override and user_override.get("user_set") and user_override.get("status") in STATUSES:
        return {
            "item_id": str(item.id),
            "category": item.category,
            "title": item.title,
            "status": user_override["status"],
            "reason": user_override.get("reason") or "Updated by you.",
            "user_set": True,
        }

    item_id = str(item.id)
    category = (item.category or "").lower()
    details = item.details or {}
    title = item.title or "Untitled"
    title_l = title.lower()

    if item_id in duplicate_ids:
        return {
            "item_id": item_id,
            "category": category,
            "title": title,
            "status": "needs_clarification",
            "reason": "Looks similar to another vault item — confirm whether to keep both.",
            "user_set": False,
        }

    if category == "skill":
        if any(title_l in s or s in title_l for s in assessed_subjects if s):
            return {
                "item_id": item_id,
                "category": category,
                "title": title,
                "status": "confirmed",
                "reason": "Supported by a completed interview assessment on a related track.",
                "user_set": False,
            }
        return {
            "item_id": item_id,
            "category": category,
            "title": title,
            "status": "not_assessed",
            "reason": "Listed on your profile, but not yet evaluated in a technical interview.",
            "user_set": False,
        }

    if category == "project":
        missing = missing_project_details(details)
        if missing:
            return {
                "item_id": item_id,
                "category": category,
                "title": title,
                "status": "needs_clarification",
                "reason": "Still missing: " + ", ".join(missing[:4]) + ".",
                "user_set": False,
            }
        if any(title_l in s or s in title_l for s in assessed_subjects if s):
            return {
                "item_id": item_id,
                "category": category,
                "title": title,
                "status": "confirmed",
                "reason": "Project details are filled and a related interview assessment exists.",
                "user_set": False,
            }
        return {
            "item_id": item_id,
            "category": category,
            "title": title,
            "status": "not_assessed",
            "reason": "Details are on file, but technical depth has not been interview-assessed yet.",
            "user_set": False,
        }

    if category in ("education", "internship", "achievement"):
        if not (title or "").strip():
            return {
                "item_id": item_id,
                "category": category,
                "title": title,
                "status": "needs_clarification",
                "reason": "Title is empty — add a clearer label.",
                "user_set": False,
            }
        return {
            "item_id": item_id,
            "category": category,
            "title": title,
            "status": "confirmed",
            "reason": "Captured from your resume or conversation as profile information.",
            "user_set": False,
        }

    return {
        "item_id": item_id,
        "category": category,
        "title": title,
        "status": "needs_clarification",
        "reason": "Please confirm what this item represents.",
        "user_set": False,
    }


def build_profile_summary(items: list, prefs: dict | None) -> str:
    """Natural summary using only persisted facts — no invented biography."""
    p = normalize_preferences(prefs)
    by_cat: dict[str, list] = {}
    for item in items:
        by_cat.setdefault((item.category or "other").lower(), []).append(item)

    lines = [
        "Here's what I understood about you from your resume and our conversation.",
        "",
    ]

    if by_cat.get("education"):
        titles = ", ".join(i.title for i in by_cat["education"][:4])
        lines.append(f"Education: {titles}.")
    if by_cat.get("internship"):
        titles = ", ".join(i.title for i in by_cat["internship"][:4])
        lines.append(f"Experience / internships: {titles}.")
    if by_cat.get("skill"):
        titles = ", ".join(i.title for i in by_cat["skill"][:8])
        extra = len(by_cat["skill"]) - 8
        if extra > 0:
            titles += f", and {extra} more"
        lines.append(
            f"Skills on file: {titles}. "
            "These are listed for practice — they are not treated as proven proficiency yet."
        )
    if by_cat.get("project"):
        bits = []
        for i in by_cat["project"][:4]:
            missing = missing_project_details(i.details or {})
            note = " (details incomplete)" if missing else ""
            bits.append(f"{i.title}{note}")
        lines.append("Projects: " + "; ".join(bits) + ".")
    if by_cat.get("achievement"):
        titles = ", ".join(i.title for i in by_cat["achievement"][:4])
        lines.append(f"Achievements: {titles}.")

    goal_text = summarize_preferences(p)
    if p.get("interests"):
        lines.append("")
        lines.append("Preparation goals:")
        lines.append(goal_text)

    lines.append("")
    lines.append(
        "Review anything that looks off — you can correct the vault or edit this summary. "
        "I will not treat assumptions as verified technical skill."
    )
    return "\n".join(lines)


def build_roadmap(
    prefs: dict | None,
    items: list,
    *,
    assessed_subjects: set[str] | None = None,
    improvement_topics: list[str] | None = None,
) -> list[dict]:
    """Ordered preparation steps from actual goals, profile, and prior interview gaps."""
    p = normalize_preferences(prefs)
    assessed = {s.lower() for s in (assessed_subjects or set()) if s}
    skills = [i.title for i in items if (i.category or "").lower() == "skill"]
    projects = [i.title for i in items if (i.category or "").lower() == "project"]
    steps: list[dict] = []

    def add(
        *,
        step_id: str,
        title: str,
        why: str,
        topics: list[str],
        practise: str,
        track_type: str,
        subject: str,
    ) -> None:
        key = subject.lower()
        if any(s["subject"].lower() == key for s in steps):
            return
        steps.append(
            {
                "id": step_id,
                "title": title,
                "why": why,
                "topics": topics,
                "practise": practise,
                "track_type": track_type,
                "subject": subject,
                "action_label": f"Start {subject}",
            }
        )

    # Prior interview improvement areas (persisted reports only — never invented scores).
    for topic in (improvement_topics or [])[:3]:
        label = str(topic).strip()
        if not label:
            continue
        add(
            step_id=f"improve-{label.lower().replace(' ', '-')[:40]}",
            title=f"Revisit: {label}",
            why="Flagged as an improvement area in a completed interview report.",
            topics=[label],
            practise=f"Targeted practice on {label} based on your prior feedback.",
            track_type="topic",
            subject=label,
        )

    focus_skills = p.get("focus_skills") or []
    for skill in focus_skills[:3]:
        add(
            step_id=f"skill-{skill.lower().replace(' ', '-')}",
            title=f"{skill} practice",
            why=f"You chose skill-based preparation and listed {skill} as a focus.",
            topics=[skill, "core concepts", "applied problem solving"],
            practise=f"Interview questions that probe how you use {skill} in real work.",
            track_type="topic",
            subject=skill,
        )

    if "skill" in p["interests"] and not focus_skills:
        for skill in skills[:2]:
            if skill.lower() in assessed:
                continue
            add(
                step_id=f"vault-skill-{skill.lower().replace(' ', '-')}",
                title=f"{skill} practice",
                why=f"{skill} is on your vault and has not been interview-assessed yet.",
                topics=[skill],
                practise=f"Confirm how you apply {skill} under interview questions.",
                track_type="topic",
                subject=skill,
            )

    if "technical" in p["interests"]:
        role = p.get("target_role") or "Technical Interview"
        areas = p.get("technical_areas") or []
        topics = areas[:4] or ["core CS fundamentals relevant to your role"]
        add(
            step_id="technical-core",
            title=f"{role} technical prep",
            why="You selected technical interview preparation"
            + (f" for {role}." if p.get("target_role") else "."),
            topics=list(topics),
            practise="Role-aligned technical questions, one area at a time.",
            track_type="role" if p.get("target_role") else "topic",
            subject=role if p.get("target_role") else (areas[0] if areas else "Technical Interview"),
        )

    focus_projects = p.get("focus_projects") or []
    if "project" in p["interests"]:
        targets = focus_projects or projects[:2]
        for proj in targets[:2]:
            add(
                step_id=f"project-{proj.lower().replace(' ', '-')[:40]}",
                title=f"{proj} deep dive",
                why="Project-based interviews help you explain architecture and your contribution.",
                topics=[proj, "architecture", "trade-offs", "personal contribution"],
                practise=f"Walk through {proj} as you would in a technical screen.",
                track_type="topic",
                subject=f"{proj} deep dive",
            )

    if "placement" in p["interests"]:
        role = p.get("target_role") or "Software Engineer Intern"
        placement = p.get("placement_target") or "internship / full-time"
        add(
            step_id="placement",
            title=f"Placement prep · {role}",
            why=f"You are preparing for {placement} opportunities.",
            topics=[role, "fundamentals", "resume storytelling"],
            practise="Mixed technical screens aligned to placement interviews.",
            track_type="role",
            subject=role,
        )

    if "behavioral" in p["interests"]:
        add(
            step_id="behavioral",
            title="HR & behavioral preparation",
            why="You selected HR and behavioral interview practice.",
            topics=["ownership stories", "conflict", "teamwork", "motivation"],
            practise="Structured behavioral answers grounded in your real experience.",
            track_type="topic",
            subject="HR & Behavioral Interviews",
        )

    # Fall back to seed recommendations if interests somehow empty after confirm.
    if not steps:
        for seed in recommend_track_seeds(p):
            add(
                step_id=f"seed-{seed['subject'].lower().replace(' ', '-')[:40]}",
                title=seed["subject"],
                why="Suggested from your preparation preferences.",
                topics=[seed["subject"]],
                practise=f"Start a track focused on {seed['subject']}.",
                track_type=seed["track_type"],
                subject=seed["subject"],
            )

    return steps[:8]


def annotate_roadmap_completion(
    roadmap: list[dict],
    *,
    existing_track_subjects: set[str] | None = None,
    assessed_subjects: set[str] | None = None,
    open_session_subjects: set[str] | None = None,
) -> list[dict]:
    """Mark each roadmap step from persisted tracks/sessions/reports only."""
    existing = {s.lower() for s in (existing_track_subjects or set()) if s}
    assessed = {s.lower() for s in (assessed_subjects or set()) if s}
    open_subs = {s.lower() for s in (open_session_subjects or set()) if s}
    out: list[dict] = []
    for index, step in enumerate(roadmap or []):
        subject = str(step.get("subject") or "").lower()
        if subject and any(subject in a or a in subject for a in assessed if a):
            completion = "completed"
        elif subject and (
            subject in open_subs
            or any(subject in o or o in subject for o in open_subs if o)
        ):
            completion = "in_progress"
        elif subject and (
            subject in existing
            or any(subject in e or e in subject for e in existing if e)
        ):
            completion = "in_progress"
        else:
            completion = "not_started"
        out.append(
            {
                **step,
                "stage": index + 1,
                "completion": completion,
            }
        )
    return out


def resolve_next_action(
    *,
    open_sessions: list[dict] | None = None,
    needs_clarification: list[dict] | None = None,
    roadmap: list[dict] | None = None,
    existing_tracks: list[dict] | None = None,
    improvement_topics: list[str] | None = None,
) -> dict | None:
    """Single reusable resolver for the dashboard primary CTA.

    Priority:
    1. Resume an open interview
    2. Clarify important profile/project gaps
    3. Create the first recommended track if none exist
    4. Practise weak concepts from real interview reports
    5. Recommend another relevant track
    Never creates tracks/sessions by itself.
    """
    sessions = list(open_sessions or [])
    if sessions:
        row = sessions[0]
        subject = row.get("track_subject") or "your interview"
        return {
            "kind": "resume_session",
            "title": f"Resume your open interview on {subject}.",
            "reason": (
                f"You have an unfinished session"
                f" (Q{row.get('question_index', '?')}/{row.get('max_turns', '?')},"
                f" {row.get('answered_count', 0)} answered)."
            ),
            "action_label": "Resume Interview",
            "session_id": row.get("session_id"),
            "track_id": row.get("track_id"),
            "subject": subject,
            "href": f"/tracks/{row.get('track_id')}/interview/{row.get('session_id')}",
        }

    clarify = [
        c
        for c in (needs_clarification or [])
        if isinstance(c, dict)
        and (c.get("category") or "").lower() in ("project", "education", "other")
    ]
    if not clarify:
        clarify = [c for c in (needs_clarification or []) if isinstance(c, dict)]
    if clarify:
        first = clarify[0]
        title = first.get("title") or "a vault item"
        return {
            "kind": "clarify_profile",
            "title": f"Clarify “{title}” before your next interview.",
            "reason": first.get("reason")
            or "Some profile details are incomplete or conflicting.",
            "action_label": "Fix in vault",
            "item_id": first.get("item_id"),
            "subject": title,
            "href": "/onboarding",
        }

    tracks = [t for t in (existing_tracks or []) if isinstance(t, dict) and t.get("subject")]
    track_by_subject = {str(t["subject"]).lower(): t for t in tracks}
    steps = list(roadmap or [])

    if not tracks:
        step = steps[0] if steps else None
        if step:
            return {
                "kind": "create_track",
                "title": (
                    f"Based on your profile and goals, I recommend starting with"
                    f" {step['subject']}."
                ),
                "reason": step.get("why") or "Create your first preparation track.",
                "action_label": "Start Recommended Interview",
                "track_type": step.get("track_type") or "topic",
                "subject": step["subject"],
                "step_id": step.get("id"),
            }
        return {
            "kind": "create_track",
            "title": "Create your first preparation track to begin practising.",
            "reason": "No tracks yet — pick a subject aligned to your goals.",
            "action_label": "Create a track",
            "track_type": "topic",
            "subject": "",
            "href": "/#new-track",
        }

    for topic in improvement_topics or []:
        label = str(topic).strip()
        if not label:
            continue
        match = None
        for subject, track in track_by_subject.items():
            if label.lower() in subject or subject in label.lower():
                match = track
                break
        if match:
            return {
                "kind": "practise_weakness",
                "title": f"Practise “{label}” — flagged in your interview feedback.",
                "reason": "Based on a completed assessment, not a guessed proficiency score.",
                "action_label": "Practise weak area",
                "subject": label,
                "track_id": match.get("id"),
                "href": f"/tracks/{match.get('id')}",
            }
        return {
            "kind": "practise_weakness",
            "title": f"Practise “{label}” — flagged in your interview feedback.",
            "reason": "Based on a completed assessment, not a guessed proficiency score.",
            "action_label": "Start focused practice",
            "track_type": "topic",
            "subject": label,
        }

    for step in steps:
        subject = str(step.get("subject") or "")
        existing = track_by_subject.get(subject.lower())
        if existing is None:
            return {
                "kind": "recommend_track",
                "title": (
                    f"Based on your profile and goals, I recommend starting with {subject}."
                ),
                "reason": step.get("why") or "Next step on your preparation roadmap.",
                "action_label": "Start Recommended Interview",
                "track_type": step.get("track_type") or "topic",
                "subject": subject,
                "step_id": step.get("id"),
            }
        if step.get("completion") != "completed":
            return {
                "kind": "recommend_track",
                "title": f"Continue with {subject} — you already have a related track.",
                "reason": step.get("why") or "Open your existing preparation track.",
                "action_label": "Open Recommended Track",
                "track_type": step.get("track_type") or "topic",
                "subject": subject,
                "step_id": step.get("id"),
                "track_id": existing.get("id"),
                "reuse_existing": True,
                "href": f"/tracks/{existing.get('id')}",
            }

    if steps:
        step = steps[0]
        existing = track_by_subject.get(str(step.get("subject") or "").lower())
        return {
            "kind": "recommend_track",
            "title": f"Continue with {step.get('subject')} — you already have a related track.",
            "reason": step.get("why") or "Revisit your primary preparation track.",
            "action_label": "Open Recommended Track",
            "track_type": step.get("track_type") or "topic",
            "subject": step.get("subject"),
            "step_id": step.get("id"),
            "track_id": (existing or {}).get("id"),
            "reuse_existing": True,
            "href": f"/tracks/{(existing or {}).get('id')}" if existing else None,
        }
    return None


def pick_next_action(roadmap: list[dict], existing_track_subjects: set[str] | None = None) -> dict | None:
    """Backward-compatible wrapper around resolve_next_action."""
    tracks = [{"subject": s} for s in (existing_track_subjects or set()) if s]
    return resolve_next_action(roadmap=roadmap, existing_tracks=tracks)


def _preserve_if_incomplete(previous: dict, review: dict) -> dict:
    """Never replace a usable review with an empty/incomplete rebuild."""
    prev = previous or {}
    out = dict(review)
    new_summary = (out.get("summary") or "").strip()
    prev_summary = (prev.get("summary") or "").strip()
    if not new_summary and prev_summary:
        out["summary"] = prev["summary"]
        out["summary_user_edit"] = prev.get("summary_user_edit")
    if not (out.get("roadmap") or []) and (prev.get("roadmap") or []):
        out["roadmap"] = prev["roadmap"]
        out["next_action"] = prev.get("next_action") or out.get("next_action")
    if not out.get("selected_next_track_id") and prev.get("selected_next_track_id"):
        out["selected_next_track_id"] = prev["selected_next_track_id"]
    return out


def build_review(
    items: list,
    prefs: dict | None,
    *,
    previous: dict | None = None,
    assessed_subjects: set[str] | None = None,
    existing_track_subjects: set[str] | None = None,
    existing_tracks: list[dict] | None = None,
    open_sessions: list[dict] | None = None,
    improvement_topics: list[str] | None = None,
    force_summary: bool = False,
) -> dict:
    """Compose a full review document. Preserves user summary edits and status overrides."""
    previous = previous or {}
    prefs_n = normalize_preferences(prefs)
    fp = vault_fingerprint(items)
    assessed = {s.lower() for s in (assessed_subjects or set()) if s}
    tracks = list(existing_tracks or [])
    if not tracks and existing_track_subjects:
        tracks = [{"subject": s} for s in existing_track_subjects if s]
    track_subjects = {
        str(t.get("subject") or "") for t in tracks if t.get("subject")
    } | {str(s) for s in (existing_track_subjects or set()) if s}
    open_rows = list(open_sessions or [])
    open_subjects = {
        str(r.get("track_subject") or "") for r in open_rows if r.get("track_subject")
    }

    duplicate_ids: set[str] = set()
    for pair in find_near_duplicates(items):
        duplicate_ids.add(pair["a"]["id"])
        duplicate_ids.add(pair["b"]["id"])

    prev_statuses = {
        str(s.get("item_id")): s
        for s in (previous.get("item_statuses") or [])
        if isinstance(s, dict) and s.get("item_id")
    }

    item_statuses = [
        classify_item(
            item,
            duplicate_ids=duplicate_ids,
            assessed_subjects=assessed,
            user_override=prev_statuses.get(str(item.id)),
        )
        for item in items
    ]
    needs_clarification = [
        s for s in item_statuses if s["status"] == "needs_clarification"
    ]

    user_summary = (previous.get("summary_user_edit") or "").strip() or None
    if user_summary and not force_summary:
        summary = user_summary
        summary_user_edit = user_summary
    else:
        # Keep prior AI summary if vault unchanged and user did not force refresh.
        if (
            previous.get("vault_fingerprint") == fp
            and (previous.get("summary") or "").strip()
            and not force_summary
            and not user_summary
        ):
            summary = previous["summary"]
        else:
            summary = build_profile_summary(items, prefs_n)
        summary_user_edit = None

    roadmap = build_roadmap(
        prefs_n,
        items,
        assessed_subjects=assessed,
        improvement_topics=improvement_topics,
    )
    # Keep prior roadmap if a rebuild somehow produced nothing.
    if not roadmap and (previous.get("roadmap") or []):
        roadmap = list(previous["roadmap"])
    roadmap = annotate_roadmap_completion(
        roadmap,
        existing_track_subjects=track_subjects,
        assessed_subjects=assessed,
        open_session_subjects=open_subjects,
    )
    next_action = resolve_next_action(
        open_sessions=open_rows,
        needs_clarification=needs_clarification,
        roadmap=roadmap,
        existing_tracks=tracks,
        improvement_topics=improvement_topics,
    )

    review = {
        "summary": summary,
        "summary_user_edit": summary_user_edit,
        "item_statuses": item_statuses,
        "needs_clarification": needs_clarification,
        "not_assessed": [s for s in item_statuses if s["status"] == "not_assessed"],
        "confirmed": [s for s in item_statuses if s["status"] == "confirmed"],
        "roadmap": roadmap,
        "next_action": next_action,
        "selected_next_track_id": previous.get("selected_next_track_id"),
        "preparation_summary": summarize_preferences(prefs_n),
        "goal_labels": [
            GOAL_INTEREST_LABELS.get(i, i) for i in prefs_n.get("interests") or []
        ],
        "vault_fingerprint": fp,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return _preserve_if_incomplete(previous, review)


def merge_review_patch(current: dict, patch: dict) -> dict:
    """Apply user corrections without wiping generated roadmap unless asked."""
    out = dict(current or {})
    if "summary" in patch and patch["summary"] is not None:
        text = str(patch["summary"]).strip()[:8000]
        out["summary"] = text
        out["summary_user_edit"] = text
    if "selected_next_track_id" in patch:
        out["selected_next_track_id"] = patch["selected_next_track_id"]
    if "item_statuses" in patch and isinstance(patch["item_statuses"], list):
        by_id = {
            str(s.get("item_id")): s
            for s in (out.get("item_statuses") or [])
            if isinstance(s, dict)
        }
        for upd in patch["item_statuses"]:
            if not isinstance(upd, dict) or not upd.get("item_id"):
                continue
            status = upd.get("status")
            if status not in STATUSES:
                continue
            item_id = str(upd["item_id"])
            base = by_id.get(item_id, {"item_id": item_id, "title": "", "category": ""})
            base = {
                **base,
                "status": status,
                "reason": str(upd.get("reason") or "Updated by you.")[:500],
                "user_set": True,
            }
            by_id[item_id] = base
        out["item_statuses"] = list(by_id.values())
        out["needs_clarification"] = [
            s for s in out["item_statuses"] if s["status"] == "needs_clarification"
        ]
        out["not_assessed"] = [
            s for s in out["item_statuses"] if s["status"] == "not_assessed"
        ]
        out["confirmed"] = [s for s in out["item_statuses"] if s["status"] == "confirmed"]
    out["updated_at"] = datetime.now(UTC).isoformat()
    return out


def empty_review() -> dict[str, Any]:
    return {
        "summary": "",
        "summary_user_edit": None,
        "item_statuses": [],
        "needs_clarification": [],
        "not_assessed": [],
        "confirmed": [],
        "roadmap": [],
        "next_action": None,
        "selected_next_track_id": None,
        "preparation_summary": "",
        "goal_labels": [],
        "vault_fingerprint": "",
        "generated_at": None,
    }
