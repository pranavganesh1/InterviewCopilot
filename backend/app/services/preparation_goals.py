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

# Stable substring used to detect that the goals intro was already seeded.
GOALS_INTRO_MARKER = "What would you like to focus on"

PROJECT_ASPECT_OPTIONS: list[tuple[str, str]] = [
    ("architecture", "Project architecture"),
    ("implementation", "Technical implementation"),
    ("challenges", "Challenges and solutions"),
    ("technologies", "Technologies used"),
    ("research", "Research contributions"),
    ("deep_dive", "Complete project deep dive"),
]

EMPTY_PREFERENCES: dict = {
    "interests": [],
    "target_role": None,
    "technical_areas": [],
    "focus_skills": [],
    "focus_projects": [],
    "project_aspects": [],
    "placement_target": None,
    "experience_level": None,
    "behavioral_goals": None,
    "confirmed": False,
}

_SKILL_ROLE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("machine learning", "ml", "deep learning", "pytorch", "tensorflow", "nlp"), "ML Engineer"),
    (("data science", "pandas", "numpy", "statistics"), "Data Scientist"),
    (("react", "frontend", "javascript", "typescript", "next.js"), "Frontend Developer"),
    (("node", "django", "flask", "fastapi", "spring", "backend"), "Backend Developer"),
    (("full stack", "mern", "mean"), "Full Stack Developer"),
    (("android", "kotlin", "swift", "ios", "flutter", "react native"), "Mobile Developer"),
    (("aws", "azure", "gcp", "devops", "docker", "kubernetes"), "Cloud / DevOps Engineer"),
    (("sql", "postgres", "mongodb", "database"), "Software Engineer"),
    (("python", "java", "c++", "golang", "go"), "Software Engineer"),
]


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

    # Prefer known aspect ids; still allow free-text labels the UI may send.
    clean_aspects: list[str] = []
    for a in _str_list("project_aspects"):
        if a not in clean_aspects:
            clean_aspects.append(a)

    base.update(
        {
            "interests": clean_interests,
            "target_role": _opt_str("target_role"),
            "technical_areas": _str_list("technical_areas"),
            "focus_skills": _str_list("focus_skills"),
            "focus_projects": _str_list("focus_projects"),
            "project_aspects": clean_aspects[:12],
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
    for key in (
        "interests",
        "technical_areas",
        "focus_skills",
        "focus_projects",
        "project_aspects",
    ):
        if key in update and isinstance(update[key], list):
            nxt[key] = normalize_preferences({key: update[key]})[key]
    if "confirmed" in update:
        nxt["confirmed"] = bool(update["confirmed"])
    return nxt


def preferences_ready(prefs: dict | None) -> bool:
    p = normalize_preferences(prefs)
    return bool(p["interests"]) and bool(p["confirmed"])


def next_goal_followup(prefs: dict | None) -> str | None:
    """Next resume-aware follow-up step id, or None when details are complete."""
    p = normalize_preferences(prefs)
    interests = p["interests"]
    if not interests:
        return "interests"
    if "technical" in interests and not p["target_role"]:
        return "technical_role"
    if "technical" in interests and not p["technical_areas"]:
        return "technical_areas"
    if "skill" in interests and not p["focus_skills"]:
        return "skills"
    if "project" in interests and not p["focus_projects"]:
        return "projects"
    if "project" in interests and p["focus_projects"] and not p["project_aspects"]:
        return "project_aspects"
    if "placement" in interests and not p["placement_target"]:
        return "placement_target"
    if "placement" in interests and not p["target_role"]:
        return "placement_role"
    if "behavioral" in interests and not (
        p["experience_level"] or p["behavioral_goals"]
    ):
        return "behavioral"
    return None


def followups_complete(prefs: dict | None) -> bool:
    return next_goal_followup(prefs) is None and bool(
        normalize_preferences(prefs)["interests"]
    )


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
    if p["project_aspects"]:
        label_map = dict(PROJECT_ASPECT_OPTIONS)
        lines.append(
            "Project focus: "
            + ", ".join(label_map.get(a, a) for a in p["project_aspects"])
        )
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
        subject = p["target_role"] or (
            p["technical_areas"][0] if p["technical_areas"] else "Technical Interview"
        )
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


def _titles(summary: list[dict], category: str) -> list[str]:
    out: list[str] = []
    for item in summary or []:
        if item.get("category") != category:
            continue
        title = str(item.get("title") or "").strip()
        if title and title not in out:
            out.append(title)
    return out


def _split_techs(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        vals = [str(v).strip() for v in raw]
    else:
        text = str(raw).replace(";", ",").replace("/", ",")
        vals = [p.strip() for p in text.split(",")]
    out: list[str] = []
    for v in vals:
        if v and v not in out:
            out.append(v[:80])
    return out


def _project_techs(item: dict) -> list[str]:
    details = item.get("details") or {}
    if not isinstance(details, dict):
        return []
    for key in ("technologies", "tech_stack", "stack", "tools"):
        techs = _split_techs(details.get(key))
        if techs:
            return techs
    return []


def skill_titles(summary: list[dict]) -> list[str]:
    return _titles(summary, "skill")


def project_titles(summary: list[dict]) -> list[str]:
    return _titles(summary, "project")


def suggest_technical_areas(summary: list[dict]) -> list[str]:
    """Resume-derived practice areas (skills + project technologies + gentle extras)."""
    areas: list[str] = []
    for skill in skill_titles(summary):
        if skill not in areas:
            areas.append(skill)
    for item in summary or []:
        if item.get("category") != "project":
            continue
        for tech in _project_techs(item):
            if tech not in areas:
                areas.append(tech)
    # Add a few complementary topics when resume signals them — not proficiency claims.
    blob = " ".join(a.lower() for a in areas)
    extras: list[str] = []
    if any(k in blob for k in ("python", "java", "c++", "dsa", "algorithm")):
        extras.append("Data Structures & Algorithms")
    if any(k in blob for k in ("system", "distributed", "backend", "microservice")):
        extras.append("System Design")
    if any(k in blob for k in ("sql", "postgres", "mysql", "mongodb", "database")):
        extras.append("Databases / SQL")
    if any(k in blob for k in ("ml", "machine learning", "pytorch", "tensorflow")):
        extras.append("ML fundamentals")
    for e in extras:
        if e not in areas:
            areas.append(e)
    return areas[:16]


def suggest_roles(summary: list[dict]) -> list[str]:
    """Cautious role suggestions from internship titles and skill/project keywords."""
    roles: list[str] = []
    for title in _titles(summary, "internship"):
        # Internship titles are often already role-like.
        cleaned = title.strip()
        if cleaned and cleaned not in roles:
            roles.append(cleaned[:80])

    skills_blob = " ".join(s.lower() for s in skill_titles(summary))
    for item in summary or []:
        if item.get("category") == "project":
            skills_blob += " " + " ".join(t.lower() for t in _project_techs(item))
            purpose = str((item.get("details") or {}).get("purpose") or "").lower()
            skills_blob += " " + purpose

    for keywords, role in _SKILL_ROLE_HINTS:
        if any(k in skills_blob for k in keywords) and role not in roles:
            roles.append(role)
        if len(roles) >= 8:
            break

    # Soft defaults when resume is sparse — still optional chips, not assumptions.
    for fallback in ("Software Engineer Intern", "Software Engineer"):
        if fallback not in roles:
            roles.append(fallback)
    return roles[:8]


def project_option_cards(summary: list[dict]) -> list[dict]:
    """Structured project chips for the UI (label + optional subtitle from tech)."""
    cards: list[dict] = []
    for item in summary or []:
        if item.get("category") != "project":
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        techs = _project_techs(item)
        purpose = str((item.get("details") or {}).get("purpose") or "").strip()
        subtitle = ", ".join(techs[:4]) if techs else (purpose[:100] if purpose else "")
        cards.append(
            {
                "id": title,
                "label": title,
                "subtitle": subtitle,
                "technologies": techs,
            }
        )
    return cards


def build_resume_goal_options(vault_summary: list[dict]) -> dict:
    """Structured dynamic options for GET /onboarding/state (no new routes)."""
    skills = skill_titles(vault_summary)
    projects = project_titles(vault_summary)
    return {
        "goal_interest_options": [
            {"id": i, "label": label} for i, label in GOAL_INTERESTS
        ],
        "suggested_skills": skills,
        "suggested_projects": projects,
        "suggested_roles": suggest_roles(vault_summary),
        "suggested_technical_areas": suggest_technical_areas(vault_summary),
        "project_options": project_option_cards(vault_summary),
        "project_aspect_options": [
            {"id": i, "label": label} for i, label in PROJECT_ASPECT_OPTIONS
        ],
        "resume_highlights": {
            "skills": skills[:6],
            "projects": projects[:4],
            "education": _titles(vault_summary, "education")[:2],
            "internships": _titles(vault_summary, "internship")[:2],
        },
    }


def goals_intro_message(vault_summary: list[dict] | None = None) -> str:
    """Personalized transition into goal discovery (resume-aware)."""
    summary = vault_summary or []
    skills = skill_titles(summary)
    projects = project_titles(summary)

    if skills and projects:
        skill_preview = ", ".join(skills[:3])
        proj = projects[0]
        return (
            f"I noticed you've worked with {skill_preview}, and your “{proj}” project "
            "looks interesting! Let's personalize your preparation. "
            f"{GOALS_INTRO_MARKER}? You can pick more than one."
        )
    if skills:
        skill_preview = ", ".join(skills[:4])
        return (
            f"I noticed {skill_preview} in your profile. "
            "Let's personalize your preparation. "
            f"{GOALS_INTRO_MARKER}? You can pick more than one."
        )
    if projects:
        named = ", ".join(f"“{p}”" for p in projects[:3])
        return (
            f"I found these projects in your resume: {named}. "
            "Let's personalize your preparation. "
            f"{GOALS_INTRO_MARKER}? You can pick more than one."
        )
    return (
        "Your profile looks good! Now let's personalize your interview preparation. "
        f"{GOALS_INTRO_MARKER} first? You can pick more than one."
    )


# Backward-compatible alias used by older checks / imports.
GOALS_INTRO = goals_intro_message([])


def goals_followup_reply(
    prefs: dict | None,
    vault_summary: list[dict] | None = None,
) -> str:
    """Deterministic coach follow-up when the LLM is unavailable."""
    p = normalize_preferences(prefs)
    summary = vault_summary or []
    skills = skill_titles(summary)
    projects = project_titles(summary)
    areas = suggest_technical_areas(summary)
    roles = suggest_roles(summary)

    if not p["interests"]:
        return (
            "Pick one or more preparation focuses above and I will tailor the next questions."
        )
    focus = ", ".join(GOAL_INTEREST_LABELS.get(i, i) for i in p["interests"])

    if "technical" in p["interests"] and not p.get("target_role"):
        hint = f" Suggestions from your background: {', '.join(roles[:3])}." if roles else ""
        return (
            f"Great — focusing on {focus}. "
            f"Which role are you targeting?{hint}"
        )
    if "technical" in p["interests"] and not p.get("technical_areas"):
        if areas:
            preview = ", ".join(areas[:4])
            return (
                f"I noticed {preview} in your profile. "
                "Which technical areas would you like to practice?"
            )
        return (
            "Thanks. Which technical areas should we emphasize "
            "(for example DSA, system design, or backend)?"
        )
    if "skill" in p["interests"] and not p.get("focus_skills"):
        if skills:
            preview = ", ".join(skills[:4])
            return (
                f"Your resume mentions {preview}. "
                "Which skill would you like to test first?"
            )
        return "Which skills from your vault do you want to practise first?"
    if "project" in p["interests"] and not p.get("focus_projects"):
        if projects:
            named = ", ".join(f"“{p_}”" for p_ in projects[:3])
            return (
                f"I found these projects in your resume: {named}. "
                "Which one would you like to prepare for interviews?"
            )
        return "Which project should we deep-dive in interviews?"
    if (
        "project" in p["interests"]
        and p.get("focus_projects")
        and not p.get("project_aspects")
    ):
        chosen = p["focus_projects"][0]
        card = next(
            (c for c in project_option_cards(summary) if c["label"] == chosen),
            None,
        )
        tech_bit = ""
        if card and card.get("technologies"):
            tech_bit = (
                f" uses {', '.join(card['technologies'][:4])} and"
            )
        return (
            f"I noticed your “{chosen}” project{tech_bit}. "
            "Would you like to practice explaining its architecture, technical challenges, "
            "implementation, or research contributions?"
        )
    if "placement" in p["interests"] and not p.get("placement_target"):
        return "Are you preparing for internship, full-time, or both?"
    if "placement" in p["interests"] and not p.get("target_role"):
        hint = f" Based on your background: {', '.join(roles[:3])}." if roles else ""
        return f"Which roles are you targeting?{hint} You can also type a custom role."
    if "behavioral" in p["interests"] and not (
        p.get("experience_level") or p.get("behavioral_goals")
    ):
        return "For HR and behavioral prep, what experience level should we target?"
    return (
        f"Nice — your preparation focus is set ({focus}). "
        "Tap Start Preparing when you're ready, or tell me any adjustments."
    )
