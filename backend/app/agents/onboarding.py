from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion
from app.services.preparation_goals import (
    EMPTY_PREFERENCES,
    GOAL_INTEREST_LABELS,
    merge_preferences,
    normalize_preferences,
    preferences_ready,
)

ITEM_CATEGORIES = Literal["project", "internship", "skill", "achievement", "education", "other"]

ITEM_CATEGORIES_SET = {
    "project",
    "internship",
    "skill",
    "achievement",
    "education",
    "other",
}

SYSTEM_PROMPT = """You are the InterviewCopilot onboarding coach (profile phase).

You receive:
- known_vault_summary: existing profile items with details, source, and missing_details
- possible_duplicates: near-duplicate titles that need confirmation (do not merge silently)
- profile_gaps: categories still missing or projects missing detail fields
- conversation_mode: optional focus (ai_interview | explore_projects | test_skills | career_goal)
- conversation_so_far / new_user_message

Hard rules:
1. Ask exactly ONE useful question per reply (max 3 short sentences). Never re-ask a
   question that is already answered in conversation_so_far or known_vault_summary.
2. Never invent facts. Only extract what the student clearly said.
3. Short replies ("yes", "yeah", "ok", "okay", "sure", "no", "skip", "not sure",
   "I don't remember") MUST be interpreted using the last assistant question:
   - Affirmative → confirm the pending fact; do NOT re-ask the same question.
   - Skip / don't remember → accept the gap; move to the next missing field.
   - Bare "yes" is NEVER a complete project description.
4. If the user gives only a project title, save it as a partial project (title only)
   and ask one specific follow-up (purpose → technologies → architecture/features →
   contribution → outcome). Collect those progressively; keep partials.
5. Prefer profile_gaps. Do not ask for categories already complete unless the student
   volunteers an update. Dig into missing_details on existing projects first.
6. For possible_duplicates, ask whether they are the same item or distinct. Do not
   silently merge or delete.
7. After successfully saving information, do NOT ask for confirmation again — thank
   them briefly and move to the next gap.
8. Set phase="profile" until project AND skill AND education exist. When they do,
   set phase="goals", show_goal_menu=true, and briefly invite them to pick interview
   preparation goals (the UI shows the choices).
9. extracted_items: use the taxonomy; details hold short factual keys.
10. Leave preparation_update empty during profile phase unless the user volunteers goals.
11. conversation_mode guidance (still onboarding — never invent scores/assessments):
   - ai_interview: natural warm-up interview; introduce yourself briefly then ask about
     education/skills/projects from the vault one question at a time; dig into architecture,
     decisions, challenges, and personal contribution.
   - explore_projects: deep-dive a vault project; never invent tech/results.
   - test_skills: explore available_skills only; ask which to practise.
   - career_goal: discover role/placement/skills/projects/behavioral prep; fill
     preparation_update when stated.
"""

GOALS_SYSTEM_PROMPT = """You are the InterviewCopilot preparation coach (goals phase).

The profile vault is already complete. Discover what the candidate wants to practice.

You receive known_vault_summary, available_skills, available_projects,
current_preparation_preferences, conversation_so_far, and new_user_message.

Interest ids: technical, skill, project, placement, behavioral.

Rules:
1. Ask exactly ONE follow-up at a time. Never re-ask answered details.
2. Do not re-collect resume facts already in known_vault_summary.
3. Interpret short yes/no/skip answers from conversation context.
4. Contextual follow-ups:
   - technical → target role and technical areas
   - skill → which of available_skills to practice (do not invent skills)
   - project → which of available_projects to interview on
   - placement → internship, full-time, or both
   - behavioral → experience level and interview goals
5. Multiple interests are allowed. Fill preparation_update with any newly stated fields.
6. When interests are chosen and the needed follow-ups for those interests are covered,
   set preparation_update.confirmed=true, phase="ready", and give a concise summary.
7. show_goal_menu=true only when interests are still empty.
8. extracted_items should usually be empty in this phase.
9. reply: warm, concise (max 3 sentences).
"""

FINISHED_SYSTEM_PROMPT = """You are the InterviewCopilot profile coach. This student has
already finished onboarding. They are revisiting to edit or enrich their vault or goals.

Rules:
- Do NOT restart the intake questionnaire.
- Acknowledge updates briefly. Ask at most one clarifying question when needed.
- Interpret short yes/no/skip answers from conversation context.
- Record new vault facts in extracted_items; goal changes in preparation_update.
- Always set phase="ready" and onboarding_complete=true.
"""


class ExtractedItem(BaseModel):
    category: ITEM_CATEGORIES
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


class PreparationUpdate(BaseModel):
    interests: list[str] | None = None
    target_role: str | None = None
    technical_areas: list[str] | None = None
    focus_skills: list[str] | None = None
    focus_projects: list[str] | None = None
    placement_target: str | None = None
    experience_level: str | None = None
    behavioral_goals: str | None = None
    confirmed: bool | None = None


class OnboardingTurn(BaseModel):
    reply: str
    extracted_items: list[ExtractedItem] = []
    onboarding_complete: bool = False
    phase: Literal["profile", "goals", "ready"] = "profile"
    show_goal_menu: bool = False
    preparation_update: PreparationUpdate | None = None


class OnboardingState(TypedDict, total=False):
    message: str
    history: list[dict]
    vault_summary: list[dict]
    possible_duplicates: list[dict]
    profile_gaps: dict
    preparation_preferences: dict
    available_skills: list[str]
    available_projects: list[str]
    conversation_mode: str
    already_finished: bool
    phase: str
    meta: dict
    turn: dict


def compute_profile_gaps(vault_summary: list[dict]) -> dict:
    cats = {str(i.get("category") or "") for i in vault_summary}
    missing_categories = [c for c in ("project", "skill", "education") if c not in cats]
    incomplete_projects = [
        {
            "title": i.get("title"),
            "missing_details": i.get("missing_details") or [],
        }
        for i in vault_summary
        if i.get("category") == "project" and (i.get("missing_details") or [])
    ]
    return {
        "missing_categories": missing_categories,
        "incomplete_projects": incomplete_projects,
    }


def vault_is_ready(vault_summary: list[dict]) -> bool:
    cats = {str(i.get("category") or "") for i in vault_summary}
    return {"project", "skill", "education"}.issubset(cats)


def derive_phase(
    *,
    vault_summary: list[dict],
    preferences: dict | None,
    already_finished: bool,
) -> str:
    if already_finished or preferences_ready(preferences):
        return "ready"
    if vault_is_ready(vault_summary):
        return "goals"
    return "profile"


async def run_onboarding_turn(
    *,
    message: str,
    history: list[dict],
    vault_summary: list[dict],
    already_finished: bool = False,
    possible_duplicates: list[dict] | None = None,
    profile_gaps: dict | None = None,
    preparation_preferences: dict | None = None,
    available_skills: list[str] | None = None,
    available_projects: list[str] | None = None,
    conversation_mode: str | None = None,
    phase: str | None = None,
    meta: dict | None = None,
) -> OnboardingTurn:
    """One LLM decision for onboarding (profile intake or goal discovery)."""
    prior = list(history or [])
    if prior and prior[-1].get("role") == "user" and prior[-1].get("content") == message:
        prior = prior[:-1]

    prefs = normalize_preferences(preparation_preferences)
    mode = (conversation_mode or "").strip() or None
    current_phase = phase or derive_phase(
        vault_summary=vault_summary,
        preferences=prefs,
        already_finished=already_finished,
    )
    # Starters choose the coach: career goals vs exploratory warm-up.
    if not already_finished:
        if mode == "career_goal":
            current_phase = "goals"
        elif mode in ("ai_interview", "explore_projects", "test_skills"):
            # Keep the profile/exploration coach even when the vault is already ready.
            current_phase = "profile"

    payload = {
        "known_vault_summary": vault_summary,
        "possible_duplicates": possible_duplicates or [],
        "profile_gaps": profile_gaps or compute_profile_gaps(vault_summary),
        "current_preparation_preferences": prefs,
        "available_skills": available_skills or [],
        "available_projects": available_projects or [],
        "goal_interest_labels": GOAL_INTEREST_LABELS,
        "conversation_mode": mode,
        "conversation_so_far": prior[-18:],
        "new_user_message": message,
        "already_finished": already_finished,
        "phase": current_phase,
    }

    if already_finished:
        system = FINISHED_SYSTEM_PROMPT
    elif current_phase in ("goals", "ready"):
        system = GOALS_SYSTEM_PROMPT
    else:
        system = SYSTEM_PROMPT

    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        turn = await structured_completion(
            client,
            system=system,
            user_payload=payload,
            schema=OnboardingTurn,
            meta=meta,
        )

    # Deterministic phase / completion after the model replies.
    merged_prefs = prefs
    if turn.preparation_update is not None:
        merged_prefs = merge_preferences(prefs, turn.preparation_update.model_dump(exclude_none=True))

    cats = {str(i.get("category") or "") for i in vault_summary}
    for item in turn.extracted_items:
        cats.add(item.category)
    vault_ready = {"project", "skill", "education"}.issubset(cats)

    if already_finished:
        turn.phase = "ready"
        turn.onboarding_complete = True
        turn.show_goal_menu = False
    elif preferences_ready(merged_prefs):
        turn.phase = "ready"
        turn.onboarding_complete = True
        turn.show_goal_menu = False
    elif mode in ("ai_interview", "explore_projects", "test_skills"):
        # Exploration starters stay in conversational profile mode; goals UI waits.
        turn.phase = "profile"
        turn.onboarding_complete = False
        turn.show_goal_menu = False
    elif vault_ready or mode == "career_goal":
        turn.phase = "goals"
        turn.onboarding_complete = False
        if not merged_prefs["interests"]:
            turn.show_goal_menu = True
    else:
        turn.phase = "profile"
        turn.onboarding_complete = False
        turn.show_goal_menu = False

    return turn


def build_onboarding_graph(turn_runner=run_onboarding_turn):
    """Compile the intake graph. turn_runner is injectable for tests."""

    async def intake(state: OnboardingState) -> dict:
        turn = await turn_runner(
            message=state["message"],
            history=state.get("history", []),
            vault_summary=state.get("vault_summary", []),
            already_finished=bool(state.get("already_finished")),
            possible_duplicates=state.get("possible_duplicates"),
            profile_gaps=state.get("profile_gaps"),
            preparation_preferences=state.get("preparation_preferences") or EMPTY_PREFERENCES,
            available_skills=state.get("available_skills"),
            available_projects=state.get("available_projects"),
            conversation_mode=state.get("conversation_mode"),
            phase=state.get("phase"),
            meta=state.get("meta"),
        )
        return {"turn": turn.model_dump()}

    graph = StateGraph(OnboardingState)
    graph.add_node("intake", intake)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", END)
    return graph.compile()
