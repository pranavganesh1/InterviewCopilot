from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion

SYSTEM_PROMPT = """You are InterviewCopilot's interviewer conducting a STRICT interview.

Rules:
- Ask ONE question at a time. Questions must be concrete and answerable in text.
- Follow the question_areas from the brief. Do not repeat questions already asked.
- After each answer: evaluate coverage honestly, then either ask ONE follow-up probing
  a gap, move to the next area, or decide the interview is complete.
- HARD LIMIT: at most one follow-up per area. If turns_in_current_area >= 2 you MUST
  choose next_area (from remaining_areas) or complete — never another follow-up.
- Prefer depth on the candidate's own claimed projects (see candidate_angle_notes).
- STRICT mode: never give hints, teaching, or the correct answer.
- notes_for_report: 1-2 sentence evidence note for the feedback agent.
"""


class AnswerEvaluation(BaseModel):
    coverage: Literal["none", "partial", "good", "excellent"]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class TurnDecision(BaseModel):
    evaluation: AnswerEvaluation
    decision: Literal["follow_up", "next_area", "complete"]
    next_question: str
    question_area: str
    notes_for_report: str = ""


class InterviewerState(TypedDict, total=False):
    payload: dict
    decision: dict


async def run_interviewer_turn(*, payload: dict) -> TurnDecision:
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        return await structured_completion(
            client, system=SYSTEM_PROMPT, user_payload=payload, schema=TurnDecision
        )


def build_interviewer_graph(turn_runner=run_interviewer_turn):
    async def evaluate(state: InterviewerState) -> dict:
        decision = await turn_runner(payload=state["payload"])
        return {"decision": decision.model_dump()}

    graph = StateGraph(InterviewerState)
    graph.add_node("evaluate", evaluate)
    graph.add_edge(START, "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()
