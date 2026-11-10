from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion

ITEM_CATEGORIES = Literal["project", "internship", "skill", "achievement", "education", "other"]

ITEM_CATEGORIES_SET = {
    "project",
    "internship",
    "skill",
    "achievement",
    "education",
    "other",
}

SYSTEM_PROMPT = """You are the InterviewCopilot onboarding coach.

You receive:
- known_vault_summary: existing profile items with details, source, and missing_details
- possible_duplicates: near-duplicate titles that need confirmation (do not merge silently)
- profile_gaps: categories still missing or projects missing detail fields
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
8. Set onboarding_complete=true only when project AND skill AND education exist in
   known_vault_summary (after applying this turn's extractions_items).
9. extracted_items: use the taxonomy; details hold short factual keys
   (purpose, technologies, architecture, contribution, outcome, features, level, etc.).
   Re-emit an item with the same title to enrich details — do not invent new titles for
   the same project.
"""

FINISHED_SYSTEM_PROMPT = """You are the InterviewCopilot profile coach. This student has
already finished onboarding. They are revisiting to edit or enrich their vault.

Rules:
- Do NOT restart the intake questionnaire or re-ask for projects, skills, or education
  they already have in known_vault_summary.
- Acknowledge updates briefly. Ask at most one clarifying question only when the new
  detail is incomplete.
- Interpret short yes/no/skip answers from conversation context; never loop the same ask.
- Whenever they share concrete new information, record it in extracted_items.
- For possible_duplicates, ask which to keep — never silently merge.
- reply must be warm and concise (max 3 sentences). Prefer confirmation over probing.
- Always set onboarding_complete=true.
"""


class ExtractedItem(BaseModel):
    category: ITEM_CATEGORIES
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


class OnboardingTurn(BaseModel):
    reply: str
    extracted_items: list[ExtractedItem] = []
    onboarding_complete: bool = False


class OnboardingState(TypedDict, total=False):
    message: str
    history: list[dict]
    vault_summary: list[dict]
    possible_duplicates: list[dict]
    profile_gaps: dict
    already_finished: bool
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


async def run_onboarding_turn(
    *,
    message: str,
    history: list[dict],
    vault_summary: list[dict],
    already_finished: bool = False,
    possible_duplicates: list[dict] | None = None,
    profile_gaps: dict | None = None,
    meta: dict | None = None,
) -> OnboardingTurn:
    """One LLM decision for the onboarding intake (conversation + extraction)."""
    # History already includes the just-appended user message; avoid duplicating it
    # inside conversation_so_far when present as the last entry.
    prior = list(history or [])
    if prior and prior[-1].get("role") == "user" and prior[-1].get("content") == message:
        prior = prior[:-1]

    payload = {
        "known_vault_summary": vault_summary,
        "possible_duplicates": possible_duplicates or [],
        "profile_gaps": profile_gaps or compute_profile_gaps(vault_summary),
        "conversation_so_far": prior[-18:],
        "new_user_message": message,
        "already_finished": already_finished,
    }
    system = FINISHED_SYSTEM_PROMPT if already_finished else SYSTEM_PROMPT
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        turn = await structured_completion(
            client,
            system=system,
            user_payload=payload,
            schema=OnboardingTurn,
            meta=meta,
        )
    if already_finished:
        turn.onboarding_complete = True
    else:
        # Prefer vault facts over the model's guess when categories are already filled.
        cats = {str(i.get("category") or "") for i in vault_summary}
        for item in turn.extracted_items:
            cats.add(item.category)
        if {"project", "skill", "education"}.issubset(cats):
            turn.onboarding_complete = True
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
            meta=state.get("meta"),
        )
        return {"turn": turn.model_dump()}

    graph = StateGraph(OnboardingState)
    graph.add_node("intake", intake)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", END)
    return graph.compile()
