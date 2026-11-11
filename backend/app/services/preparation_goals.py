"""Preparation-goal helpers shared by onboarding agent, API, and dashboard."""

from __future__ import annotations

GOAL_INTERESTS: list[tuple[str, str]] = [
    ("technical", "Technical Interview Preparation"),
    ("skill", "Skill-Based Practice"),
    ("project", "Project-Based Interviews"),
    ("placement", "Internship & Placement Preparation"),
    ("behavioral", "HR and Behavioral Interviews"),
]

GOAL_INTEREST_IDS = {i for i, _ in GOAL_INTERESTS}
GOAL_INTEREST_LABELS = dict(GOAL_INTERESTS)

EMPTY_PREFERENCES: dict = {
    "interests": [],
    "target_role": None,
    "technical_areas": [],
    "focus_skills": [],
    "focus_projects": [],
    "placement_target": None,
    "experience_level": None,
    "behavioral_goals": None,
    "confirmed": False,
}


def normalize_preferences(raw: dict | None) -> dict:
    base = dict(EMPTY_PREFERENCES)
    if not isinstance(raw, dict):
        return base
    interests = [
        str(i)
        for i in (raw.get("interests") or [])
        if str(i) in GOAL_INTEREST_IDS
    ]
    # de-dupe preserve order
    seen: set[str] = set()
    clean_interests: list[str] = []
    for i in interests:
        if i not in seen:
            seen.add(i)
            clean_interests.append(i)

    def _str_list(key: str) -> list[str]:
        vals = raw.get(key) or []
        if not isinstance(vals, list):
            return []
        out: list[str] = []
        for v in vals:
            s = str(v).strip()
            if s and s not in out:
                out.append(s[:120])
        return out[:20]

    def _opt_str(key: str) -> str | None:
        v = raw.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s[:255] if s else None

    base.update(
        {
            "interests": clean_interests,
            "target_role": _opt_str("target_role"),
            "technical_areas": _str_list("technical_areas"),
            "focus_skills": _str_list("focus_skills"),
            "focus_projects": _str_list("focus_projects"),
            "placement_target": _opt_str("placement_target"),
            "experience_level": _opt_str("experience_level"),
            "behavioral_goals": _opt_str("behavioral_goals"),
            "confirmed": bool(raw.get("confirmed")),
        }
    )
    return base


def merge_preferences(existing: dict | None, update: dict | None) -> dict:
    cur = normalize_preferences(existing)
    if not update:
        return cur
    nxt = normalize_preferences({**cur, **{k: v for k, v in update.items() if v is not None}})
    # Empty lists in update should clear only when explicitly provided as list.
    for key in ("interests", "technical_areas", "focus_skills", "focus_projects"):
        if key in update and isinstance(update[key], list):
            nxt[key] = normalize_preferences({key: update[key]})[key]
    if "confirmed" in update:
        nxt["confirmed"] = bool(update["confirmed"])
    return nxt


def preferences_ready(prefs: dict | None) -> bool:
    p = normalize_preferences(prefs)
    return bool(p["interests"]) and bool(p["confirmed"])


def summarize_preferences(prefs: dict | None) -> str:
    p = normalize_preferences(prefs)
    if not p["interests"]:
        return "No preparation goals selected yet."
    lines = [
        "Preparation focus: "
        + ", ".join(GOAL_INTEREST_LABELS.get(i, i) for i in p["interests"])
    ]
    if p["target_role"]:
        lines.append(f"Target role: {p['target_role']}")
    if p["technical_areas"]:
        lines.append("Technical areas: " + ", ".join(p["technical_areas"]))
    if p["focus_skills"]:
        lines.append("Skills to practice: " + ", ".join(p["focus_skills"]))
    if p["focus_projects"]:
        lines.append("Projects to discuss: " + ", ".join(p["focus_projects"]))
    if p["placement_target"]:
        lines.append(f"Placement target: {p['placement_target']}")
    if p["experience_level"]:
        lines.append(f"Experience level: {p['experience_level']}")
    if p["behavioral_goals"]:
        lines.append(f"Behavioral goals: {p['behavioral_goals']}")
    return "\n".join(lines)


def recommend_track_seeds(prefs: dict | None) -> list[dict]:
    """Lightweight track suggestions for the dashboard create form."""
    p = normalize_preferences(prefs)
    seeds: list[dict] = []
    if "technical" in p["interests"]:
        subject = p["target_role"] or (p["technical_areas"][0] if p["technical_areas"] else "Technical Interview")
        seeds.append({"track_type": "role" if p["target_role"] else "topic", "subject": subject})
    if "skill" in p["interests"]:
        for skill in p["focus_skills"][:3]:
            seeds.append({"track_type": "topic", "subject": skill})
    if "project" in p["interests"]:
        for proj in p["focus_projects"][:2]:
            seeds.append({"track_type": "topic", "subject": f"{proj} deep dive"})
    if "placement" in p["interests"]:
        seeds.append(
            {
                "track_type": "role",
                "subject": p["target_role"] or "Software Engineer Intern",
            }
        )
    if "behavioral" in p["interests"]:
        seeds.append({"track_type": "topic", "subject": "HR & Behavioral Interviews"})
    # de-dupe by subject
    seen: set[str] = set()
    out: list[dict] = []
    for s in seeds:
        key = s["subject"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out[:6]


GOALS_INTRO = (
    "Your profile looks good! Now let's personalize your interview preparation. "
    "What would you like to focus on first? You can pick more than one."
)


def goals_followup_reply(prefs: dict | None) -> str:
    """Deterministic coach follow-up when the LLM is unavailable."""
    p = normalize_preferences(prefs)
    if not p["interests"]:
        return (
            "Pick one or more preparation focuses above and I will tailor the next questions."
        )
    focus = ", ".join(GOAL_INTEREST_LABELS.get(i, i) for i in p["interests"])
    if "technical" in p["interests"] and not p.get("target_role"):
        return (
            f"Great — focusing on {focus}. "
            "What target role are you aiming for?"
        )
    if "technical" in p["interests"] and not p.get("technical_areas"):
        return (
            "Thanks. Which technical areas should we emphasize "
            "(for example DSA, system design, or backend)?"
        )
    if "skill" in p["interests"] and not p.get("focus_skills"):
        return "Which skills from your vault do you want to practise first?"
    if "project" in p["interests"] and not p.get("focus_projects"):
        return "Which project should we deep-dive in interviews?"
    if "placement" in p["interests"] and not p.get("placement_target"):
        return "Are you preparing for internship, full-time, or both?"
    if "behavioral" in p["interests"] and not (
        p.get("experience_level") or p.get("behavioral_goals")
    ):
        return "For HR and behavioral prep, what experience level should we target?"
    return (
        f"Nice — your preparation focus is set ({focus}). "
        "Tap Start Preparing when you're ready, or tell me any adjustments."
    )
