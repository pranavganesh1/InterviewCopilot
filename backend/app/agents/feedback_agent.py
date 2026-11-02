from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion

EVIDENCE_PROMPT = """You are InterviewCopilot's evidence extractor. For each question-answer
pair in a completed interview, extract evidence.

Rules:
- coverage: how completely the answer addresses the question (none/partial/good/excellent).
- observation: one factual sentence about what the answer demonstrated or missed.
- evidence_excerpt: a SHORT verbatim quote from the answer supporting the observation
  (empty string if the answer gave nothing quotable).
- Ground everything in the actual transcript. Never invent answers or claims.
"""

ASSESS_PROMPT = """You are InterviewCopilot's assessment writer. Using the extracted
evidence and the interview brief's competencies, produce the feedback report.

Rules:
- competency_assessments: one entry per brief competency. Only mark ASSESSED when real
  evidence exists; topics never probed are NOT_ASSESSED, and questions outside the brief's
  competencies go to unassessed_topics. Scores must reflect evidence, not potential.
- level: weak / developing / solid / strong (null when not ASSESSED).
- strengths and improvement_areas: concrete, grounded in the transcript.
- recommendations: 3-5 specific practice actions for the student.
- summary_overview: 2-3 sentences a student would find fair and useful.
- STRICT interview: treat every answer as unassisted evidence.
"""


class QuestionEvidence(BaseModel):
    turn_index: int
    coverage: Literal["none", "partial", "good", "excellent"]
    observation: str
    evidence_excerpt: str = ""


class AssessedCompetency(BaseModel):
    competency_name: str
    assessment_status: Literal[
        "ASSESSED", "PARTIALLY_ASSESSED", "NOT_ASSESSED", "INSUFFICIENT_EVIDENCE"
    ]
    level: Literal["weak", "developing", "solid", "strong"] | None = None
    observation: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class FeedbackReportContent(BaseModel):
    report_version: int = 1
    session_mode: Literal["strict", "guided"]
    summary_overview: str
    coverage_status: Literal["COMPLETE", "PARTIAL", "MINIMAL"]
    question_assessments: list[QuestionEvidence] = Field(default_factory=list)
    competency_assessments: list[AssessedCompetency] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    unassessed_topics: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class EvidenceState(TypedDict, total=False):
    payload: dict
    evidence: dict
    report: dict


async def run_feedback_agent(*, payload: dict) -> FeedbackReportContent:
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        evidence = await structured_completion(
            client,
            system=EVIDENCE_PROMPT,
            user_payload=payload,
            schema=_EvidenceList,
        )
        return await structured_completion(
            client,
            system=ASSESS_PROMPT,
            user_payload={**payload, "extracted_evidence": evidence.model_dump()["items"]},
            schema=FeedbackReportContent,
        )


class _EvidenceItem(BaseModel):
    turn_index: int = 0
    coverage: Literal["none", "partial", "good", "excellent"] = "none"
    observation: str = ""
    evidence_excerpt: str = ""


class _EvidenceList(BaseModel):
    items: list[_EvidenceItem] = Field(default_factory=list)


def build_feedback_graph(turn_runner=run_feedback_agent):
    async def assess(state: EvidenceState) -> dict:
        content = await turn_runner(payload=state["payload"])
        return {"report": content.model_dump()}

    graph = StateGraph(EvidenceState)
    graph.add_node("assess", assess)
    graph.add_edge(START, "assess")
    graph.add_edge("assess", END)
    return graph.compile()
