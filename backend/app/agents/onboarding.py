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

SYSTEM_PROMPT = """You are the InterviewCopilot onboarding interviewer. Your job is to
truly understand the student behind the resume.

Rules:
- Ask about ONE thing at a time: their projects (problem, their personal role, methods,
  alternatives considered, what failed, how they evaluated results, limitations, what
  they would improve now), internships, skills, achievements, and education.
- Dig below surface claims. "Built an AI system" is a start; ask what problem it solved,
  what THEY implemented, and what did not work.
- Whenever the student shares concrete information, record it in extracted_items using
  the category taxonomy. details must hold short factual key points.
- reply must be warm, concise (max 3 sentences), and ask exactly one follow-up question.
- Set onboarding_complete=true only when you have projects AND skills AND education.
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
    turn: dict


async def run_onboarding_turn(
    *, message: str, history: list[dict], vault_summary: list[dict]
) -> OnboardingTurn:
    """One LLM decision for the onboarding intake (conversation + extraction)."""
    payload = {
        "known_vault_summary": vault_summary,
        "conversation_so_far": history,
        "new_user_message": message,
    }
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        return await structured_completion(
            client,
            system=SYSTEM_PROMPT,
            user_payload=payload,
            schema=OnboardingTurn,
        )


def build_onboarding_graph(turn_runner=run_onboarding_turn):
    """Compile the intake graph. turn_runner is injectable for tests."""

    async def intake(state: OnboardingState) -> dict:
        turn = await turn_runner(
            message=state["message"],
            history=state.get("history", []),
            vault_summary=state.get("vault_summary", []),
        )
        return {"turn": turn.model_dump()}

    graph = StateGraph(OnboardingState)
    graph.add_node("intake", intake)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", END)
    return graph.compile()
