"""Per-session question plan: distinct topics/objectives for each interview turn.

Used as soft guidance in the interviewer payload. Falls back to a deterministic
plan from the brief when the LLM call fails or returns invalid output.
"""

from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.question_quality import active_profile, format_for_slot, is_programming_brief
from app.core.logging import get_logger
from app.gateway.structured import structured_completion

log = get_logger(__name__)

Difficulty = Literal["foundational", "intermediate", "advanced"]

_PLAN_SYSTEM = """You are InterviewCopilot's interview planner.
Given a brief, produce exactly N distinct question slots for a timed interview.

Rules:
- Each slot must cover a DIFFERENT learning objective (no paraphrases of the same ask).
- Schedule subjects in CONSECUTIVE BLOCKS (finish one subject before the next).
  Short interviews: smaller blocks across fewer subjects. Longer interviews: more
  subjects and slightly deeper blocks. Do not round-robin one slot per topic.
- Cover MULTIPLE relevant subjects from the brief — never spend the whole plan
  on one concept. Derive subjects from question_areas / competencies / resume
  areas and the candidate's actual background (any discipline: CS, engineering,
  sciences, commerce, arts, career-switch paths). Do not assume Computer Science.
- Difficulty arc overall: early foundational, middle intermediate, late advanced.
  Within a subject block, deepen gradually across distinct concepts.
- topic: short subject/area label; objective: one concrete concept to probe.
- Stay inside the track. Do not invent unrelated domains.
- When prior_areas is present, prefer areas that are not in that list.
- prior_questions are short texts already asked on this track. Do not repeat them.
- When avoid_areas is present and the brief has another area, the first slot
  must use one of those other areas.
- Respect duration_minutes when choosing how many subjects to cover.
"""

# Field-agnostic facets used only when the brief is too thin to diversify.
# Labels stay generic so Physics/Commerce/Arts/CS tracks can share the planner.
_DIVERSITY_FACETS: tuple[tuple[str, str], ...] = (
    ("Foundations", "Core concepts and definitions for this field"),
    ("Methods and tools", "Standard methods, tools, or techniques used in practice"),
    ("Applied problem-solving", "Applying knowledge to a realistic problem"),
    ("Analysis and judgment", "Comparing approaches, evaluating trade-offs, or critique"),
    ("Experience and application", "Practical experience, projects, or workplace application"),
)


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


def target_subject_count(n: int, duration_minutes: int | None = None) -> int:
    """How many distinct subjects a session of n slots should aim to cover."""
    n = max(0, int(n))
    if n <= 0:
        return 0
    mins = int(duration_minutes) if duration_minutes is not None else 60
    mins = max(15, min(mins, 240))
    if mins <= 30:
        soft_cap = 4
    elif mins <= 60:
        soft_cap = 6
    else:
        soft_cap = 8
    # At least 2 subjects when there is room; never more than n // 2.
    return max(1, min(soft_cap, max(2, n // 3) if n >= 4 else n, n))


def _enrich_topics(
    brief_content: dict, topics: list[str], *, need: int
) -> list[str]:
    """Grow a thin topic list with brief-derived / field-agnostic subjects."""
    out = list(topics)
    seen = {t.lower() for t in out}

    def _add(name: str) -> None:
        text = (name or "").strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    # Guidance phrases often name distinct sub-areas already in the brief.
    for qa in brief_content.get("question_areas") or []:
        if len(out) >= need:
            break
        guidance = (qa.get("guidance") or "").strip()
        if not guidance:
            continue
        # First clause / short guidance as a subject label when distinct.
        label = guidance.split(".")[0].split(",")[0].strip()
        if 3 <= len(label) <= 60:
            _add(label)

    summary = (brief_content.get("summary") or "").strip()
    if summary and len(out) < need:
        first = summary.split(".")[0].strip()
        if 3 <= len(first) <= 60:
            _add(first)

    angle = (brief_content.get("candidate_angle_notes") or "").strip()
    if angle and len(out) < need:
        first = angle.split(".")[0].split(";")[0].strip()
        if 3 <= len(first) <= 60:
            _add(first)

    for label, _guidance in _DIVERSITY_FACETS:
        if len(out) >= need:
            break
        _add(label)

    return out[: max(need, len(topics))]


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


def _questions_per_topic(
    n: int, n_topics: int, *, duration_minutes: int | None = None
) -> int:
    """Consecutive questions per subject; shorter sessions use smaller blocks."""
    if n_topics <= 0:
        return max(2, n)
    mins = int(duration_minutes) if duration_minutes is not None else 60
    lo, hi = (2, 3) if mins <= 30 else (2, 4)
    return max(lo, min(hi, (n + n_topics - 1) // n_topics))


def _blocked_topic_sequence(
    topics: list[str], n: int, *, duration_minutes: int | None = None
) -> list[str]:
    """Repeat each topic in a consecutive block, then advance to the next."""
    if n <= 0:
        return []
    if not topics:
        return ["Core concepts"] * n
    per = _questions_per_topic(n, len(topics), duration_minutes=duration_minutes)
    seq: list[str] = []
    index = 0
    while len(seq) < n:
        topic = topics[index % len(topics)]
        for _ in range(per):
            if len(seq) >= n:
                break
            seq.append(topic)
        index += 1
    return seq


def topic_block_size(plan: list | None, topic: str | None) -> int:
    """Longest consecutive run for topic in the plan (clamped to 2–5)."""
    if not isinstance(plan, list) or not topic:
        return 3
    needle = topic.strip().lower()
    if not needle:
        return 3
    best = 0
    run = 0
    for slot in plan:
        if not isinstance(slot, dict):
            run = 0
            continue
        name = (slot.get("topic") or "").strip().lower()
        if name == needle:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return max(2, min(5, best or 3))


def plan_topics(plan: list | None) -> list[str]:
    """Stable unique subject labels from a persisted question plan."""
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(plan, list):
        return out
    for slot in plan:
        if not isinstance(slot, dict):
            continue
        topic = (slot.get("topic") or "").strip()
        key = topic.lower()
        if topic and key not in seen:
            seen.add(key)
            out.append(topic)
    return out


def next_distinct_plan_topic(
    plan: list | None, *, questions_asked: int, current: str | None
) -> str | None:
    """First planned subject after the current index that differs from current."""
    if not isinstance(plan, list):
        return None
    current_key = (current or "").strip().lower()
    start = max(0, int(questions_asked))
    for i in range(start, len(plan)):
        slot = plan[i]
        if not isinstance(slot, dict):
            continue
        topic = (slot.get("topic") or "").strip()
        if topic and topic.lower() != current_key:
            return topic
    return None


def deterministic_question_plan(
    brief_content: dict,
    n: int,
    seed: str | None = None,
    *,
    duration_minutes: int | None = None,
) -> list[dict]:
    """Build n slots from brief topics/competencies without an LLM call.

    Subjects are scheduled in consecutive blocks so the interview finishes
    enough depth on one area before moving on. Thin briefs are enriched so a
    session cannot collapse onto a single subject. A seed rotates topic order.
    """
    n = max(0, int(n))
    brief = brief_content or {}
    mins = brief.get("duration_minutes") if duration_minutes is None else duration_minutes
    try:
        mins_i = int(mins) if mins is not None else 60
    except (TypeError, ValueError):
        mins_i = 60
    topics = _topics_from_brief(brief)
    need = target_subject_count(n, mins_i)
    # Enrich only when the session has room for real multi-subject depth
    # (>=2 questions per subject). Tiny plans and deliberately focused
    # single-area briefs stay as authored.
    if len(topics) < need and n >= max(4, need * 2):
        topics = _enrich_topics(brief, topics, need=need)
    plan_seed = seed or brief.get("plan_seed")
    if plan_seed and len(topics) > 1:
        rng = random.Random(str(plan_seed))
        shift = rng.randrange(len(topics))
        topics = topics[shift:] + topics[:shift]
        if len(topics) > 2:
            left, right = rng.sample(range(len(topics)), 2)
            topics[left], topics[right] = topics[right], topics[left]
    topics = _steer_topics(topics, _avoid_names(brief))
    profile = active_profile(brief)
    programming = is_programming_brief(brief)
    topic_seq = _blocked_topic_sequence(topics, n, duration_minutes=mins_i)
    slots: list[dict] = []
    for i, topic in enumerate(topic_seq):
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


async def build_question_plan(
    brief_content: dict,
    n: int,
    *,
    allow_llm: bool = False,
    duration_minutes: int | None = None,
) -> list[dict]:
    """Return exactly n plan slots; never raises.

    Startup uses the deterministic plan by default (allow_llm=False) so the first
    question is not blocked on a second LLM call / rate-limit cascade. Pass
    allow_llm=True when an offline enrichment path wants an LLM plan.
    """
    n = max(0, int(n))
    if n == 0:
        return []

    brief = brief_content or {}
    mins = duration_minutes if duration_minutes is not None else brief.get("duration_minutes")
    fallback = deterministic_question_plan(
        brief, n, seed=brief.get("plan_seed"), duration_minutes=mins
    )
    if not allow_llm:
        return fallback

    try:
        # max_attempts=1 + short timeout: fail FAST into the deterministic plan.
        result = await structured_completion(
            system=_PLAN_SYSTEM,
            max_attempts=1,
            repair_attempts=0,
            max_tokens=700,
            timeout_s=6.0,
            user_payload={
                "n": n,
                "duration_minutes": mins if mins is not None else 60,
                "target_subjects": target_subject_count(
                    n, int(mins) if mins is not None else 60
                ),
                "brief": {
                    "summary": (brief.get("summary") or "")[:400],
                    "question_areas": brief.get("question_areas", []),
                    "competencies": brief.get("competencies", []),
                    "candidate_angle_notes": (brief.get("candidate_angle_notes") or "")[
                        :300
                    ],
                    "prior_areas": brief.get("prior_areas") or [],
                    "prior_questions": (brief.get("prior_questions") or [])[-24:],
                    "avoid_areas": brief.get("avoid_areas") or [],
                },
            },
            schema=_PlanResponse,
        )
        normalized = _normalize_slots(result.slots, n)
        if normalized is not None:
            return _steer_opening(normalized, brief)
        log.warning("question_plan_invalid_llm_output", expected=n, got=len(result.slots))
    except Exception as exc:
        log.warning("question_plan_llm_failed", error=str(exc)[:200])

    return fallback


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
