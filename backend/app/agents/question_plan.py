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
- prior_questions are short texts already asked on this track. Do not repeat them.
- When avoid_areas is present and the brief has another area, the first slot
  must use one of those other areas.
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


def opening_areas_to_avoid(brief_areas: list[str], opening_areas: list[str]) -> list[str]:
    """Areas that must not open the next session while another area is still fresh.

    Once every brief area has already opened a session, only the previous
    session's opening area is avoided.
    """
    areas: list[str] = []
    for area in brief_areas:
        text = (area or "").strip()
        if text and text not in areas:
            areas.append(text)
    if len(areas) <= 1:
        return []
    used: list[str] = []
    for area in opening_areas:
        text = (area or "").strip()
        if text and text not in used:
            used.append(text)
    if not used:
        return []
    if any(area not in used for area in areas):
        return used
    return [used[-1]]


def _avoid_names(brief_content: dict) -> set[str]:
    names = {
        (area or "").strip().lower()
        for area in (brief_content or {}).get("avoid_areas") or []
        if (area or "").strip()
    }
    single = ((brief_content or {}).get("avoid_first_area") or "").strip().lower()
    if single:
        names.add(single)
    return names


def _steer_topics(topics: list[str], avoid: set[str]) -> list[str]:
    if len(topics) <= 1 or not avoid:
        return topics
    fresh = [topic for topic in topics if topic.lower() not in avoid]
    if not fresh:
        if topics[0].lower() in avoid:
            return topics[1:] + topics[:1]
        return topics
    return fresh + [topic for topic in topics if topic.lower() in avoid]


def deterministic_question_plan(brief_content: dict, n: int, seed: str | None = None) -> list[dict]:
    """Build n slots from brief topics/competencies without an LLM call.

    A seed changes the starting area and the area order inside the difficulty
    arc. No seed keeps the brief's own order, then still steps off an area
    that already opened the previous session.
    """
    n = max(0, int(n))
    topics = _topics_from_brief(brief_content)
    plan_seed = seed or (brief_content or {}).get("plan_seed")
    if plan_seed and len(topics) > 1:
        rng = random.Random(str(plan_seed))
        shift = rng.randrange(len(topics))
        topics = topics[shift:] + topics[:shift]
        if len(topics) > 2:
            left, right = rng.sample(range(len(topics)), 2)
            topics[left], topics[right] = topics[right], topics[left]
    topics = _steer_topics(topics, _avoid_names(brief_content))
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
                        "prior_questions": ((brief_content or {}).get("prior_questions") or [])[
                            -40:
                        ],
                        "avoid_areas": (brief_content or {}).get("avoid_areas") or [],
                    },
                },
                schema=_PlanResponse,
            )
        normalized = _normalize_slots(result.slots, n)
        if normalized is not None:
            return _steer_opening(normalized, brief_content or {})
        log.warning("question_plan_invalid_llm_output", expected=n, got=len(result.slots))
    except Exception as exc:
        log.warning("question_plan_llm_failed", error=str(exc))

    return deterministic_question_plan(
        brief_content or {}, n, seed=(brief_content or {}).get("plan_seed")
    )


def _steer_opening(slots: list[dict], brief_content: dict) -> list[dict]:
    """Move a fresh area into slot 0 without changing the difficulty arc."""
    avoid = _avoid_names(brief_content)
    if len(_topics_from_brief(brief_content)) <= 1 or not avoid or not slots:
        return slots
    if (slots[0].get("topic") or "").strip().lower() not in avoid:
        return slots
    for index in range(1, len(slots)):
        if (slots[index].get("topic") or "").strip().lower() in avoid:
            continue
        first = dict(slots[0])
        other = dict(slots[index])
        slots[0] = {
            **first,
            "topic": other["topic"],
            "objective": other["objective"],
        }
        slots[index] = {
            **other,
            "topic": first["topic"],
            "objective": first["objective"],
        }
        return slots
    return slots
