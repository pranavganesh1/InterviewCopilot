"""Per-session question plan: distinct topics/objectives for each interview turn.

Used as soft guidance in the interviewer payload. Falls back to a deterministic
plan from the brief when the LLM call fails or returns invalid output.
"""

from __future__ import annotations

import random
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.agents.question_quality import active_profile, format_for_slot, is_programming_brief
from app.core.config import get_settings
from app.core.logging import get_logger
from app.gateway.structured import structured_completion

log = get_logger(__name__)

Difficulty = Literal["foundational", "intermediate", "advanced"]

_PLAN_SYSTEM = """You are InterviewCopilot's interview planner.
Given a brief, produce exactly N distinct question slots for a timed interview.

Rules:
- Each slot must cover a DIFFERENT learning objective (no paraphrases of the same ask).
- Spread across the brief's question_areas / competencies.
- Difficulty arc: early foundational, middle intermediate, late advanced.
- topic: short area label; objective: one concrete thing the question should probe.
- Stay inside the track subject. Do not invent unrelated domains.
- When prior_areas is present, prefer areas that are not in that list.
"""


class PlanSlot(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=500)
    difficulty: Difficulty = "intermediate"
    format: Literal[
        "conceptual", "behavioral", "mcq", "code_read", "coding", "case_study", "numeric"
    ] = "conceptual"


class _PlanResponse(BaseModel):
    slots: list[PlanSlot] = Field(default_factory=list)


def _difficulty_for_index(i: int, n: int) -> Difficulty:
    if n <= 0:
        return "foundational"
    third = max(1, n // 3)
    if i < third:
        return "foundational"
    if i < 2 * third:
        return "intermediate"
    return "advanced"


def _topics_from_brief(brief_content: dict) -> list[str]:
    topics: list[str] = []
    for qa in brief_content.get("question_areas") or []:
        topic = (qa.get("topic") or "").strip()
        if topic and topic not in topics:
            topics.append(topic)
    for c in brief_content.get("competencies") or []:
        name = (c.get("name") or "").strip()
        if name and name not in topics:
            topics.append(name)
    if not topics:
        topics = ["Core concepts"]
    return topics


def deterministic_question_plan(
    brief_content: dict, n: int, seed: str | None = None
) -> list[dict]:
    """Build n slots from brief topics/competencies without an LLM call.

    A seed rotates which area is emphasized. No seed keeps the brief's own order.
    """
    n = max(0, int(n))
    topics = _topics_from_brief(brief_content)
    plan_seed = seed or (brief_content or {}).get("plan_seed")
    if plan_seed and len(topics) > 1:
        shift = random.Random(str(plan_seed)).randrange(len(topics))
        topics = topics[shift:] + topics[:shift]
    profile = active_profile(brief_content)
    programming = is_programming_brief(brief_content)
    slots: list[dict] = []
    for i in range(n):
        topic = topics[i % len(topics)]
        difficulty = _difficulty_for_index(i, n)
        slots.append(
            {
                "topic": topic,
                "objective": (
                    f"Assess {topic} at {difficulty} depth "
                    f"(slot {i + 1}/{n}; distinct from other slots)."
                ),
                "difficulty": difficulty,
                "format": format_for_slot(i, programming=programming, profile=profile),
            }
        )
    return slots


def _normalize_slots(raw: list[PlanSlot] | list[dict], n: int) -> list[dict] | None:
    if len(raw) != n:
        return None
    out: list[dict] = []
    seen_objectives: set[str] = set()
    for item in raw:
        if isinstance(item, PlanSlot):
            slot = item.model_dump()
        else:
            try:
                slot = PlanSlot.model_validate(item).model_dump()
            except Exception:
                return None
        key = slot["objective"].strip().lower()
        if not key or key in seen_objectives:
            return None
        seen_objectives.add(key)
        out.append(slot)
    return out


async def build_question_plan(brief_content: dict, n: int) -> list[dict]:
    """Return exactly n plan slots; never raises — falls back deterministically."""
    n = max(0, int(n))
    if n == 0:
        return []

    try:
        async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
            # max_attempts=1: fail FAST into the deterministic fallback. Waiting
            # 135s of 429 backoff inside start_session is terrible UX (M11).
            result = await structured_completion(
                client,
                system=_PLAN_SYSTEM,
                max_attempts=1,
                user_payload={
                    "n": n,
                    "brief": {
                        "summary": (brief_content or {}).get("summary", ""),
                        "question_areas": (brief_content or {}).get("question_areas", []),
                        "competencies": (brief_content or {}).get("competencies", []),
                        "candidate_angle_notes": (brief_content or {}).get(
                            "candidate_angle_notes", ""
                        ),
                        "prior_areas": (brief_content or {}).get("prior_areas") or [],
                    },
                },
                schema=_PlanResponse,
            )
        normalized = _normalize_slots(result.slots, n)
        if normalized is not None:
            return normalized
        log.warning("question_plan_invalid_llm_output", expected=n, got=len(result.slots))
    except Exception as exc:
        log.warning("question_plan_llm_failed", error=str(exc))

    return deterministic_question_plan(
        brief_content or {}, n, seed=(brief_content or {}).get("plan_seed")
    )
