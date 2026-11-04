"""Guided progressive assistance (conceptual + coding tracks)."""

from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion

MAX_CONCEPTUAL_LEVEL = 3
MAX_CODING_LEVEL = 5

CONCEPTUAL_LABELS: dict[int, Literal["nudge", "clue", "explanation"]] = {
    1: "nudge",
    2: "clue",
    3: "explanation",
}

CODING_LABELS: dict[
    int, Literal["hint", "approach", "pseudocode", "starter", "complete"]
] = {
    1: "hint",
    2: "approach",
    3: "pseudocode",
    4: "starter",
    5: "complete",
}

# Backward-compatible aliases used by interview_service / tests.
MAX_ASSISTANCE_LEVEL = MAX_CONCEPTUAL_LEVEL
LEVEL_LABELS = CONCEPTUAL_LABELS

_CODING_AREA = (
    "dsa",
    "algorithm",
    "coding",
    "programming",
    "array",
    "string",
    "tree",
    "graph",
    "hashmap",
    "leetcode",
    "recursion",
    "dynamic programming",
)
_CODING_QUESTION = (
    "write a function",
    "write a method",
    "implement",
    "code this",
    "given an array",
    "time complexity",
    "space complexity",
    "constraints:",
    "example 1",
)


def is_coding_question(question: str, question_area: str) -> bool:
    area = (question_area or "").lower()
    q = (question or "").lower()
    if any(k in area for k in _CODING_AREA):
        return True
    return any(k in q for k in _CODING_QUESTION)


def max_level_for_question(question: str, question_area: str) -> int:
    return (
        MAX_CODING_LEVEL
        if is_coding_question(question, question_area)
        else MAX_CONCEPTUAL_LEVEL
    )


def label_for_level(level: int, *, coding: bool) -> str:
    if coding:
        return CODING_LABELS.get(level, "hint")
    return CONCEPTUAL_LABELS.get(level, "nudge")


def next_assistance_level(current_level: int, *, max_level: int | None = None) -> int | None:
    """Backend-owned progression: ignore any client-supplied level."""
    ceiling = max_level if max_level is not None else MAX_CONCEPTUAL_LEVEL
    if current_level >= ceiling:
        return None
    return current_level + 1


CONCEPTUAL_PROMPT = """You are InterviewCopilot's Guided coach for ONE open interview question.

Produce progressive assistance at the requested level ONLY:
- level 1 (nudge): a short pointer toward a relevant concept; no steps, no answer.
- level 2 (clue): a conceptual hint that clarifies the idea without solving it.
- level 3 (explanation): a structured approach / framework the candidate can follow;
  still do not paste a full model answer.

Never reveal a complete worked solution. Stay tied to the given question and area.
"""

CODING_PROMPT = """You are InterviewCopilot's coding mentor for ONE open coding/DSA question.

Be specific and technically accurate. Never invent execution results.
Produce progressive assistance at the requested level ONLY:

- level 1 (hint): small hint about algorithm/data structure and what to think about next.
  Do NOT reveal the full approach or solution.
- level 2 (approach): step-by-step problem-solving approach, why the algorithm works,
  and expected time/space complexity. No full code.
- level 3 (pseudocode): clear pseudocode with important steps explained. No full
  language-specific solution.
- level 4 (starter): partially completed code with the required function signature;
  leave core logic as TODOs and explain what each missing section should do.
- level 5 (complete): complete working solution in the preferred language if provided
  (else Python), with line-by-line explanation, time/space complexity, and edge cases.
  Only use level 5 when requested via level=5.

Do not jump ahead: answer ONLY for the given level field.
"""


class AssistanceContent(BaseModel):
    level: int = Field(ge=1, le=5)
    assistance_type: str
    content: str = Field(min_length=1, max_length=8000)


async def generate_assistance(*, payload: dict) -> AssistanceContent:
    coding = bool(payload.get("coding"))
    system = CODING_PROMPT if coding else CONCEPTUAL_PROMPT
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        return await structured_completion(
            client,
            system=system,
            user_payload=payload,
            schema=AssistanceContent,
        )
