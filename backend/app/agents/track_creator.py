from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion

SYSTEM_PROMPT = """You are InterviewCopilot's interview architect. Design an interview
brief for a preparation track.

Rules:
- Ground everything in the objective (topic, role, or company+JD) and the candidate's
  actual vault. For company_jd tracks, derive requirements ONLY from the supplied JD text.
- competencies: what the interview should genuinely assess, with importance.
- question_areas: 8-12 areas to draw questions from; guidance states what a good answer
  covers. Include areas probing the candidate's own claimed projects (candidate_angle_notes).
- preparation_plan: 5-8 concrete study actions for the student.
- summary: one paragraph on what this interview examines and why it fits the objective.
"""


class Competency(BaseModel):
    name: str
    description: str
    importance: Literal["core", "important", "nice_to_have"]


class QuestionArea(BaseModel):
    topic: str
    guidance: str


class InterviewBriefContent(BaseModel):
    summary: str
    preparation_plan: list[str] = Field(default_factory=list)
    competencies: list[Competency] = Field(default_factory=list)
    question_areas: list[QuestionArea] = Field(default_factory=list)
    candidate_angle_notes: str = ""


class TrackCreatorState(TypedDict, total=False):
    objective: dict
    vault_summary: list[dict]
    brief: dict


async def run_track_creator_turn(
    *, objective: dict, vault_summary: list[dict]
) -> InterviewBriefContent:
    payload = {"candidate_vault": vault_summary, "track_objective": objective}
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        return await structured_completion(
            client,
            system=SYSTEM_PROMPT,
            user_payload=payload,
            schema=InterviewBriefContent,
        )


def build_track_creator_graph(turn_runner=run_track_creator_turn):
    async def author(state: TrackCreatorState) -> dict:
        content = await turn_runner(
            objective=state["objective"], vault_summary=state.get("vault_summary", [])
        )
        return {"brief": content.model_dump()}

    graph = StateGraph(TrackCreatorState)
    graph.add_node("author", author)
    graph.add_edge(START, "author")
    graph.add_edge("author", END)
    return graph.compile()
