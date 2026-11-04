from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, model_validator

from app.agents.question_dedupe import duplicate_of, is_duplicate_question, normalize_question
from app.core.config import get_settings
from app.core.logging import get_logger
from app.gateway.structured import structured_completion

log = get_logger(__name__)

_MAX_REPAIR_ATTEMPTS = 2  # initial call + up to 2 repairs = 3 LLM calls max

STRICT_SYSTEM_PROMPT = """You are InterviewCopilot's interviewer conducting a STRICT interview.

Rules:
- Ask ONE question at a time. Questions must be concrete and answerable in text.
- Follow the question_areas / track topics from the brief.
- NEVER repeat an asked question, and NEVER ask a near-paraphrase of one in
  asked_questions (different wording of the same ask still counts as a repeat).
- Compare learning objectives: if a candidate question tests the same concepts
  as any asked_questions entry (e.g. array definition + contiguous memory +
  static vs dynamic), REJECT it and pick a genuinely different concept.
- Each new question must target a DISTINCT concept or skill within the track.
  Prefer remaining_areas when non-empty; otherwise pick a new subtopic that has
  not been covered yet (see covered_areas).
- Progress difficulty with questions_asked: early questions foundational, later
  ones deeper (edge cases, complexity, trade-offs, implementation).
- Stay relevant to the selected track. Do not invent unrelated domains.
- After each answer: evaluate coverage honestly, then either ask ONE follow-up
  probing a gap, move to the next area, or decide the interview is complete.
- HARD LIMIT: at most one follow-up per area. If turns_in_current_area >= 2 you
  MUST choose next_area (from remaining_areas) or complete — never another follow-up.
- Prefer depth on the candidate's own claimed projects (see candidate_angle_notes).
- STRICT mode: never put hints, teaching, or the correct answer in next_question.
- When last_answer is present, fill evaluation thoroughly:
  strengths, gaps (mistakes / missing concepts), expected_answer_explanation.
  For coding/DSA answers also fill corrected_code, time_complexity, space_complexity.
  Keep solutions ONLY in evaluation fields — never in next_question.
- When last_answer is null (opening question), leave evaluation lists empty and
  expected_answer_explanation / corrected_code / complexities empty.
- If questions_remaining is 0, decision MUST be complete.
- notes_for_report: 1-2 sentence evidence note for the feedback agent.
"""

GUIDED_SYSTEM_PROMPT = """You are InterviewCopilot's interviewer conducting a GUIDED interview.

Rules:
- Ask ONE question at a time. Questions must be concrete and answerable in text.
- Follow the question_areas / track topics from the brief.
- NEVER repeat an asked question, and NEVER ask a near-paraphrase of one in
  asked_questions (different wording of the same ask still counts as a repeat).
- Compare learning objectives: if a candidate question tests the same concepts
  as any asked_questions entry, REJECT it and pick a genuinely different concept.
- Each new question must target a DISTINCT concept or skill within the track.
  Prefer remaining_areas when non-empty; otherwise pick a new subtopic that has
  not been covered yet (see covered_areas).
- Progress difficulty with questions_asked: early foundational, later deeper.
- Stay relevant to the selected track. Do not invent unrelated domains.
- After each answer: evaluate coverage honestly, then either ask ONE follow-up
  probing a gap, move to the next area, or decide the interview is complete.
- HARD LIMIT: at most one follow-up per area. If turns_in_current_area >= 2 you
  MUST choose next_area (from remaining_areas) or complete — never another follow-up.
- Prefer depth on the candidate's own claimed projects (see candidate_angle_notes).
- GUIDED mode: keep next_question conversational. Do NOT dump full answers or
  unsolicited multi-level teaching in next_question — progressive assistance is
  delivered only through the separate assistance API when the candidate asks.
- When last_answer is present, fill evaluation thoroughly:
  strengths, gaps (mistakes / missing concepts), expected_answer_explanation.
  For coding/DSA answers also fill corrected_code, time_complexity, space_complexity.
  Keep solutions ONLY in evaluation fields — never in next_question.
- When last_answer is null, leave evaluation extras empty.
- If questions_remaining is 0, decision MUST be complete.
- notes_for_report: 1-2 sentence evidence note for the feedback agent. Note if the
  candidate appeared to need coaching.
"""

# Backward-compatible alias used by older imports/tests.
SYSTEM_PROMPT = STRICT_SYSTEM_PROMPT


def system_prompt_for_mode(mode: str) -> str:
    if mode == "guided":
        return GUIDED_SYSTEM_PROMPT
    return STRICT_SYSTEM_PROMPT


class AnswerEvaluation(BaseModel):
    coverage: Literal["none", "partial", "good", "excellent"]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    expected_answer_explanation: str = ""
    corrected_code: str = ""
    time_complexity: str = ""
    space_complexity: str = ""


class TurnDecision(BaseModel):
    evaluation: AnswerEvaluation
    decision: Literal["follow_up", "next_area", "complete"]
    next_question: str
    question_area: str
    notes_for_report: str = ""

    @model_validator(mode="after")
    def _question_required_unless_complete(self) -> "TurnDecision":
        if self.decision != "complete" and not self.next_question.strip():
            raise ValueError("next_question is required unless decision is complete")
        if self.decision != "complete" and not self.question_area.strip():
            raise ValueError("question_area is required unless decision is complete")
        return self


class InterviewerState(TypedDict, total=False):
    payload: dict
    decision: dict


# Kept for older imports/tests.
def _norm_question(q: str) -> str:
    return normalize_question(q)


def decision_violation(decision: TurnDecision, payload: dict) -> str | None:
    """Return a human-readable violation, or None if the decision is acceptable."""
    turns_in_area = int(payload.get("turns_in_current_area") or 0)
    if decision.decision == "follow_up" and turns_in_area >= 2:
        return "follow_up not allowed when turns_in_current_area >= 2"

    remaining_slots = payload.get("questions_remaining")
    if (
        remaining_slots is not None
        and int(remaining_slots) <= 0
        and decision.decision != "complete"
    ):
        return "must complete when questions_remaining is 0"

    if decision.decision != "complete":
        asked = [q for q in payload.get("asked_questions", []) if q]
        collide = duplicate_of(decision.next_question, asked)
        if collide is not None:
            return (
                "next_question repeats or closely paraphrases a previously asked "
                f"question: {collide[:120]}"
            )
    return None


def apply_local_policy(decision: TurnDecision, payload: dict) -> TurnDecision:
    """Deterministic mode/policy fixes that do not require another LLM call."""
    turns_in_area = int(payload.get("turns_in_current_area") or 0)
    remaining = list(payload.get("remaining_areas") or [])
    remaining_slots = payload.get("questions_remaining")

    if remaining_slots is not None and int(remaining_slots) <= 0:
        return decision.model_copy(update={"decision": "complete", "next_question": ""})

    if decision.decision == "follow_up" and turns_in_area >= 2:
        if remaining:
            return decision.model_copy(
                update={
                    "decision": "next_area",
                    "question_area": remaining[0],
                }
            )
        return decision.model_copy(update={"decision": "complete", "next_question": ""})

    if decision.decision == "complete":
        return decision.model_copy(update={"next_question": decision.next_question or ""})
    return decision


_FALLBACK_STEMS = (
    "Explain the core idea behind {topic} with a concrete example.",
    "How would you implement {topic} efficiently, and what are the time and space trade-offs?",
    "Walk through an edge case involving {topic} and how you would handle it in code.",
    "Compare two approaches related to {topic} and when you would choose each.",
    "What mistakes do engineers commonly make with {topic}, and how do you avoid them?",
    "Given a realistic problem involving {topic}, outline your step-by-step solution approach.",
    "Design a small coding exercise that centers on {topic} and describe "
    "the expected solution sketch.",
    "How would you test and debug an implementation that relies on {topic}?",
)

# Distinct learning objectives for array/DSA tracks when the LLM keeps paraphrasing.
_ARRAY_CONCEPT_BANK = (
    (
        "random access",
        "Why is index-based random access O(1) in an array, and what memory property enables that?",
    ),
    (
        "insertion cost",
        "What is the time complexity of inserting at index 0 versus appending at the "
        "end of a dynamic array, and why?",
    ),
    (
        "amortized growth",
        "Explain amortized O(1) append for a dynamic array that doubles capacity on resize.",
    ),
    (
        "two pointers",
        "When would you use the two-pointer technique on a sorted array, and outline "
        "the high-level steps?",
    ),
    (
        "sliding window",
        "Describe a sliding-window approach to find the longest subarray with sum ≤ k.",
    ),
    (
        "prefix sums",
        "How do prefix sums let you answer subarray-sum queries quickly, and what is "
        "the preprocessing cost?",
    ),
    (
        "binary search",
        "State the invariants you maintain in binary search on a sorted array and why "
        "the loop terminates.",
    ),
    (
        "kadane",
        "Walk through Kadane’s algorithm for maximum subarray sum and its time/space complexity.",
    ),
    (
        "dutch flag",
        "How would you partition an array of 0/1/2 values in one pass (Dutch national flag)?",
    ),
    (
        "rotation",
        "How do you rotate an array right by k positions in-place, and what edge cases matter?",
    ),
    (
        "merge sorted",
        "Outline merging two sorted arrays into one sorted result with optimal time and space.",
    ),
    (
        "duplicates",
        "Given a sorted array, how do you remove duplicates in-place and what "
        "complexity do you achieve?",
    ),
    (
        "2d indexing",
        "How is a 2D matrix stored in row-major order, and how do you compute the "
        "flat index of cell (r, c)?",
    ),
    (
        "in-place reverse",
        "How do you reverse an array in-place, and when is that useful as a building block?",
    ),
    (
        "stability sort",
        "Why might you prefer a stable sort when sorting an array of records by one key?",
    ),
)


def _fallback_unique_question(
    payload: dict, preferred_area: str | None = None
) -> tuple[str, str] | None:
    """Build a non-duplicate question without another LLM call, or None if exhausted."""
    asked = [q for q in payload.get("asked_questions", []) if q]
    remaining = list(payload.get("remaining_areas") or [])
    covered = list(payload.get("covered_areas") or [])
    area = (
        (preferred_area or "").strip()
        or (remaining[0] if remaining else "")
        or (covered[-1] if covered else "")
        or "this track"
    )
    n = len(asked) + 1
    candidates: list[str] = []

    # Prefer a bank of genuinely different concepts (esp. Arrays tracks).
    area_l = area.lower()
    if "array" in area_l or not remaining:
        start = (n - 1) % len(_ARRAY_CONCEPT_BANK)
        for offset in range(len(_ARRAY_CONCEPT_BANK)):
            _label, question = _ARRAY_CONCEPT_BANK[(start + offset) % len(_ARRAY_CONCEPT_BANK)]
            candidates.append(question)

    # Distinct topic label per turn so soft-similarity does not collapse templates.
    topic = f"{area} — interview focus {n}"
    stem = _FALLBACK_STEMS[(n - 1) % len(_FALLBACK_STEMS)]
    candidates.append(stem.format(topic=topic))
    for extra in remaining[:5]:
        candidates.append(
            f"How does {extra} connect to {topic}, and when would you pick one over the other?"
        )
        candidates.append(
            f"Solve a short problem that requires {extra} after you already used {topic}."
        )
    candidates.append(
        f"Introduce a new concept under {topic} that was not covered in prior questions, "
        "and ask for an algorithm or explanation with complexity."
    )
    for q in candidates:
        if not is_duplicate_question(q, asked):
            return q, area
    # Absolute last resort: keep salting until soft-similarity also clears.
    for salt in range(0, 80):
        guaranteed = (
            f"Turn {n} unique-{salt} ({area}): invent a new {area} coding prompt "
            f"numbered {n}.{salt}, then outline the approach with time and space complexity."
        )
        if not is_duplicate_question(guaranteed, asked):
            return guaranteed, area
    return None


def force_unique_decision(decision: TurnDecision, payload: dict) -> TurnDecision:
    """Last-resort unique question or graceful complete — never loops forever."""
    remaining_slots = payload.get("questions_remaining")
    if remaining_slots is not None and int(remaining_slots) <= 0:
        return decision.model_copy(update={"decision": "complete", "next_question": ""})

    forced = _fallback_unique_question(payload, decision.question_area)
    if forced is None:
        log.warning(
            "question_pool_exhausted",
            asked=len(payload.get("asked_questions") or []),
        )
        return decision.model_copy(update={"decision": "complete", "next_question": ""})

    question, area = forced
    remaining = list(payload.get("remaining_areas") or [])
    return decision.model_copy(
        update={
            "decision": "next_area" if remaining else "follow_up",
            "next_question": question,
            "question_area": area,
            "notes_for_report": (
                decision.notes_for_report
                or "Forced unique question after duplicate-detection repairs."
            ),
        }
    )


async def run_interviewer_turn(*, payload: dict) -> TurnDecision:
    """Route by session mode, validate output, repair bounded times, then force-unique."""
    mode = payload.get("mode") or "strict"
    if mode not in ("strict", "guided"):
        mode = "strict"
    routed = {**payload, "mode": mode}
    system = system_prompt_for_mode(mode)

    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        decision = await structured_completion(
            client,
            system=system,
            user_payload=routed,
            schema=TurnDecision,
        )
        decision = apply_local_policy(decision, routed)
        violation = decision_violation(decision, routed)
        if violation is None:
            return decision

        for attempt in range(1, _MAX_REPAIR_ATTEMPTS + 1):
            repair_payload = {
                **routed,
                "repair_note": (
                    f"Your previous decision was rejected (attempt {attempt}): {violation}. "
                    "Choose a DIFFERENT next_question that is not identical, a paraphrase, "
                    "or the same learning objective as any asked_questions entry. Cover a "
                    "genuinely new concept (new algorithm, complexity angle, or technique). "
                    "Prefer remaining_areas. Return valid JSON only."
                ),
            }
            decision = await structured_completion(
                client,
                system=system,
                user_payload=repair_payload,
                schema=TurnDecision,
            )
            decision = apply_local_policy(decision, routed)
            violation = decision_violation(decision, routed)
            if violation is None:
                return decision

        log.warning(
            "interviewer_force_unique_after_repairs",
            violation=violation,
            asked=len(routed.get("asked_questions") or []),
        )
        forced = force_unique_decision(decision, routed)
        # Final safety: if force still somehow collides, complete.
        if forced.decision != "complete" and decision_violation(forced, routed):
            return forced.model_copy(update={"decision": "complete", "next_question": ""})
        return forced


def build_interviewer_graph(turn_runner=run_interviewer_turn):
    async def evaluate(state: InterviewerState) -> dict:
        decision = await turn_runner(payload=state["payload"])
        return {"decision": decision.model_dump()}

    graph = StateGraph(InterviewerState)
    graph.add_node("evaluate", evaluate)
    graph.add_edge(START, "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()
