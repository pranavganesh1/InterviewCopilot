from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion
from app.services.preparation_goals import (
    EMPTY_PREFERENCES,
    GOAL_INTEREST_LABELS,
    build_resume_goal_options,
    infer_candidate_background,
    merge_preferences,
    next_goal_followup,
    normalize_preferences,
    preferences_ready,
)

# Optional profile sections — never hard blockers for goals/completion.
SUGGESTED_CATEGORIES = ("project", "skill", "education")

ITEM_CATEGORIES = Literal["project", "internship", "skill", "achievement", "education", "other"]

ITEM_CATEGORIES_SET = {
    "project",
    "internship",
    "skill",
    "achievement",
    "education",
    "other",
}

SYSTEM_PROMPT = """You are the InterviewCopilot onboarding coach (profile phase) —
a friendly career mentor for candidates from ANY background (Commerce, Physics, Arts,
CS, Engineering, self-taught, fresher, career switcher, or undecided). Never assume
everyone is a Computer Science / software-engineering student.

Tone:
- Max 2–3 short sentences. One emoji is fine; never spam.
- Mention at most 1–2 concrete resume items — never dump the whole resume.
- Acknowledge answers naturally; avoid repetitive "Got it".
- Never invent education, skills, projects, jobs, or achievements.
- Resume-extracted facts are unconfirmed until the candidate affirms them.
- Never use judgmental labels (unqualified, weak, incomplete dropout, etc.).

You receive:
- candidate_background: inferred field_family + signals (not a verdict)
- coach_context: confirmed_facts, asked_questions, skipped_categories, current_topic
- known_vault_summary, possible_duplicates, profile_gaps (optional suggestions only)
- conversation_mode, conversation_so_far, new_user_message

Hard rules:
1. Ask exactly ONE useful question. Never re-ask something already answered or listed
   in coach_context.asked_questions / conversation_so_far / known_vault_summary.
   Prefer specific open questions that start with What, How, or Which (e.g. "What was
   the goal of the project, and which tools did you use?"). Never ask a yes/no question
   when you need details. If the user replies only "yes" or "no" to a detail request,
   rephrase into one concrete question with a short example — do not repeat the same ask.
   If they say they have none or say skip, accept and move on.
2. Adapt to background: Commerce → finance/analytics/business; Physics → research/
   analytical/technical options; CS → skills/projects only if resume supports it.
   Do NOT force programming/DSA questions on non-tech backgrounds unless they ask.
3. Short replies ("yes", "skip", "not sure", "I don't remember") use last question context.
   Skip / not sure → accept the gap; do not interrogate why education stopped.
4. Education, projects, internships, and achievements are OPTIONAL. If missing, ask about
   interests, self-taught skills, or goals — never repeatedly demand education.
5. If no projects: offer skill practice or interests. If no experience: focus on learning
   progress and goals. If undecided: help explore without forcing a role.
6. possible_duplicates: ask same vs distinct; never silently merge.
7. After saving a fact, thank briefly and move on — do not re-confirm.
8. When the candidate is ready for goals (or vault has any useful signal / they skip ahead),
   set phase="goals", show_goal_menu=true, and invite prep focus choices (UI shows chips).
9. extracted_items: taxonomy only; details hold short factual keys the user stated.
10. Leave preparation_update empty unless the user volunteers goals/role.
11. conversation_mode:
   - ai_interview: warm-up from THEIR vault (any field); one question at a time.
   - explore_projects: only if projects exist; never invent tech.
   - test_skills: only available_skills from vault.
   - career_goal: discover role/prep goals; fill preparation_update when stated.
12. Mentoring feedback: acknowledge what they said; one gentle follow-up. Skills listed
    on a resume do NOT prove proficiency.
"""

GOALS_SYSTEM_PROMPT = """You are the InterviewCopilot preparation coach (goals phase) —
friendly mentor for ANY field. Do not assume software engineering.

Personalize from candidate_background, vault, and preferences.

Tone examples (adapt to THEIR field; don't copy blindly):
- Commerce → "Business analyst is a solid path. Excel, SQL, or a case study first?"
- Physics → "Research or technical roles both fit analytical training — which appeals more?"
- CS with Python → "Awesome! 💻 Python or a project story first?"
- Undecided → "No rush — want skill practice, role exploration, or HR prep?"

You receive:
- candidate_background, coach_context, known_vault_summary, resume_highlights
- available_skills, available_projects, suggested_roles, suggested_technical_areas,
  suggested_prep_topics
- project_options, project_aspect_options
- current_preparation_preferences, next_goal_followup, conversation_so_far, new_user_message

Interest ids: technical, skill, project, placement, behavioral.

Rules:
1. ONE follow-up at a time. Prefer next_goal_followup. Never repeat asked_questions.
2. Do not re-collect resume facts unless confirming ambiguity.
3. Offer suggested_roles / suggested_prep_topics for THEIR field; allow any direction.
4. Mention at most 1–2 resume items. Never invent facts or claim verification.
5. If no projects: skip project deep-dive pressure; offer skills/goals/behavioral instead.
6. technical interest for non-CS → interpret as domain/analytical prep, not forced DSA,
   unless they ask for programming.
7. When follow-ups covered (next_goal_followup null), confirm prefs, phase="ready", summary.
8. show_goal_menu=true only when interests empty.
9. Warm, concise reply. Support changing focus / "I'm not sure yet" anytime.
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
    project_aspects: list[str] | None = None
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
    resume_goal_options: dict
    candidate_background: dict
    coach_context: dict
    conversation_mode: str
    already_finished: bool
    phase: str
    meta: dict
    turn: dict


def compute_profile_gaps(
    vault_summary: list[dict],
    coach_context: dict | None = None,
) -> dict:
    """Optional gaps only — missing sections are suggestions, not failures."""
    cats = {str(i.get("category") or "") for i in vault_summary}
    ctx = coach_context or {}
    skipped = {str(c) for c in (ctx.get("skipped_categories") or [])}
    na = {str(c) for c in (ctx.get("not_applicable_categories") or [])}
    missing_categories = [
        c for c in SUGGESTED_CATEGORIES if c not in cats and c not in skipped and c not in na
    ]
    incomplete_projects = [
        {
            "title": i.get("title"),
            "missing_details": i.get("missing_details") or [],
        }
        for i in vault_summary
        if i.get("category") == "project" and (i.get("missing_details") or [])
    ]
    category_status = {}
    for c in SUGGESTED_CATEGORIES:
        if c in cats:
            category_status[c] = "present"
        elif c in na:
            category_status[c] = "not_applicable"
        elif c in skipped:
            category_status[c] = "skipped"
        else:
            category_status[c] = "not_provided"
    return {
        "missing_categories": missing_categories,
        "incomplete_projects": incomplete_projects,
        "category_status": category_status,
        "optional": True,
    }


def vault_is_ready(
    vault_summary: list[dict],
    coach_context: dict | None = None,
) -> bool:
    """Unlock goals with any vault signal, or when the candidate chooses to proceed."""
    ctx = coach_context or {}
    if ctx.get("proceed_to_goals"):
        return True
    if vault_summary:
        return True
    skipped = {str(c) for c in (ctx.get("skipped_categories") or [])}
    return "vault" in skipped or set(SUGGESTED_CATEGORIES) <= skipped


def derive_phase(
    *,
    vault_summary: list[dict],
    preferences: dict | None,
    already_finished: bool,
    coach_context: dict | None = None,
) -> str:
    if already_finished or preferences_ready(preferences):
        return "ready"
    if vault_is_ready(vault_summary, coach_context):
        return "goals"
    return "profile"


def _question_fingerprint(text: str) -> str:
    cleaned = " ".join((text or "").lower().split())
    return cleaned[:180]


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
    resume_goal_options: dict | None = None,
    candidate_background: dict | None = None,
    coach_context: dict | None = None,
    conversation_mode: str | None = None,
    phase: str | None = None,
    meta: dict | None = None,
) -> OnboardingTurn:
    """One LLM decision for onboarding (profile intake or goal discovery)."""
    prior = list(history or [])
    if prior and prior[-1].get("role") == "user" and prior[-1].get("content") == message:
        prior = prior[:-1]

    prefs = normalize_preferences(preparation_preferences)
    ctx = coach_context or {}
    bg = candidate_background or infer_candidate_background(vault_summary)
    mode = (conversation_mode or "").strip() or None
    current_phase = phase or derive_phase(
        vault_summary=vault_summary,
        preferences=prefs,
        already_finished=already_finished,
        coach_context=ctx,
    )
    # Starters choose the coach: career goals vs exploratory warm-up.
    if not already_finished:
        if mode == "career_goal":
            current_phase = "goals"
        elif mode in ("ai_interview", "explore_projects", "test_skills"):
            # Keep the profile/exploration coach even when the vault is already ready.
            current_phase = "profile"

    options = resume_goal_options or build_resume_goal_options(vault_summary)
    skills = available_skills if available_skills is not None else options.get(
        "suggested_skills", []
    )
    projects = available_projects if available_projects is not None else options.get(
        "suggested_projects", []
    )

    payload = {
        "known_vault_summary": vault_summary,
        "candidate_background": bg,
        "coach_context": {
            "confirmed_facts": ctx.get("confirmed_facts") or [],
            "asked_questions": (ctx.get("asked_questions") or [])[-20:],
            "skipped_categories": ctx.get("skipped_categories") or [],
            "not_applicable_categories": ctx.get("not_applicable_categories") or [],
            "current_topic": ctx.get("current_topic"),
            "proceed_to_goals": bool(ctx.get("proceed_to_goals")),
        },
        "possible_duplicates": possible_duplicates or [],
        "profile_gaps": profile_gaps
        or compute_profile_gaps(vault_summary, coach_context=ctx),
        "current_preparation_preferences": prefs,
        "next_goal_followup": next_goal_followup(prefs),
        "available_skills": skills,
        "available_projects": projects,
        "suggested_roles": options.get("suggested_roles", []),
        "suggested_technical_areas": options.get("suggested_technical_areas", []),
        "suggested_prep_topics": options.get("suggested_prep_topics")
        or bg.get("suggested_prep_topics", []),
        "project_options": options.get("project_options", []),
        "project_aspect_options": options.get("project_aspect_options", []),
        "resume_highlights": options.get("resume_highlights", {}),
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

    # Synthetic vault after this turn's extractions items (for readiness only).
    enriched = list(vault_summary or [])
    for item in turn.extracted_items:
        enriched.append({"category": item.category, "title": item.title, "details": item.details})
    vault_ready = vault_is_ready(enriched, ctx)

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
            resume_goal_options=state.get("resume_goal_options"),
            candidate_background=state.get("candidate_background"),
            coach_context=state.get("coach_context"),
            conversation_mode=state.get("conversation_mode"),
            phase=state.get("phase"),
            meta=state.get("meta"),
        )
        payload = turn.model_dump()
        payload["_question_fingerprint"] = _question_fingerprint(turn.reply)
        return {"turn": payload}

    graph = StateGraph(OnboardingState)
    graph.add_node("intake", intake)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", END)
    return graph.compile()
