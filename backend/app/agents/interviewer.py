import re
import time
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.question_dedupe import (
    duplicate_of,
    fingerprint_tuple,
    is_duplicate_question,
    normalize_question,
)
from app.agents.question_quality import (
    CODING_STATIC_REVIEW_RULES,
    SINGLE_FOCUS_RULE,
    mcq_violation,
    numeric_violation,
    prepare_served_question,
    question_focus_violation,
    question_type_allowed,
    repair_single_focus,
    strict_praise_violation,
    strip_strict_praise,
)
from app.agents.session_pool import least_recent_text, pick_pool_question
from app.core.config import get_settings
from app.core.logging import get_logger
from app.gateway.llm import llm_model_used
from app.gateway.structured import structured_completion

log = get_logger(__name__)

_MAX_REPAIR_ATTEMPTS = 1  # initial call + 1 repair max (force_unique afterward)

PERSONA_BLOCK = """
Persona (human interviewer):
- Warm, curious, professional; light humour at most once every few questions — never mocking.
- next_question is ONLY the question. Do not store a reaction in that field.
- Ask exactly ONE concise question (max two short sentences). No lists of sub-questions.
- Use covered_so_far / memory_instruction when present.
- prior_track_questions lists questions this candidate already saw on this track.
  Do not repeat them.
"""
STRICT_REACTION_RULE = """
Strict reactions:
- Never evaluate the previous answer. Forbidden openers include "I see", "Let's explore",
  "Let's dive deeper", "Good", "Great", "Nice", "Interesting", "Right", "Okay so",
  "Exactly", "Good start", "Let's start with the basics", "That's right", and "Not quite".
- A neutral lead-in is optional and must NOT be part of next_question. Allowed spoken
  lead-ins, kept out of the stored question: "Thanks. Next topic:" / "Understood. Moving on."
  / "Let's continue with <area>."
"""
GUIDED_REACTION_RULE = """
Guided reactions:
- You may keep a short encouraging reaction in next_question, such as
  "Good start — let's go a bit deeper." Full answers still belong in the assistance API.
"""

COVERAGE_RUBRIC = """Coverage rubric:
- none      = no relevant content, or the answer is wrong
- partial   = some correct points, important parts missing or wrong
- good      = mostly correct and complete, minor gaps
- excellent = correct, complete, with sound reasoning (and complexity/edge cases where relevant)
"""

RUBRIC_VERSION = "v1"

EVALUATE_SYSTEM_PROMPT = f"""You are InterviewCopilot's answer evaluator.

Do not write the next interview question — evaluation only.

{COVERAGE_RUBRIC}
Rules:
- Judge ONLY what the candidate actually wrote. Never invent mistakes or facts.
- If probe_context is present, judge consistency with that claim or project, but
  never call a resume fact false — say uncertain instead of inventing errors.
- Judge against the stored key_points when they are present, and against
  well-established knowledge. If you are not sure a statement is wrong, put
  "uncertain" in gaps instead of inventing an error.
- Every gap must refer to something the candidate said or clearly omitted.
- Do not reward length or confident tone. Do not penalise wording differences.
- Always fill strengths, gaps, and expected_answer_explanation.
- For coding/DSA answers also fill corrected_code, time_complexity, space_complexity;
  leave those three empty for non-code answers.
- Use the track/brief context only for grounding — score against the question asked.
- Never output numeric scores; coverage labels only.
"""

_IDK_RE = re.compile(
    r"^\s*(i\s*(do\s*not|don't|dont)\s*know|idk|no\s*idea|n/?a|pass)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_FIXED_NONE_GAP = "No substantive answer was provided for this question."

STRICT_QUESTION_SYSTEM_PROMPT = (
    """You are InterviewCopilot's interviewer in STRICT mode.
"""
    + PERSONA_BLOCK
    + STRICT_REACTION_RULE
    + SINGLE_FOCUS_RULE
    + """
"""
    + COVERAGE_RUBRIC
    + """
Rules:
- Ask ONE question at a time. Questions must be concrete and answerable in text.
- Follow the question_areas / track topics from the brief.
- QUESTION BANK: question_bank holds pre-validated questions for this track.
  STRONGLY PREFER the next unused bank question matching the current or next area,
  used VERBATIM — they are already quality-checked. Improvise only for adaptive
  follow-ups, when no suitable unused bank question remains, or when the bank
  question would be a poor fit for the answer just given.
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
- After each answer: evaluate coverage honestly. Use follow_up ONLY when coverage
  is none or partial and a genuine clarification is needed. When coverage is good
  or excellent, choose next_area and ask the next planned subject/objective —
  never a soft paraphrase of the same concept.
- Depth: aim for about topic_budget questions on the current subject before
  leaving. Use question_plan_slot.topic when present — do not ignore it.
- HARD LIMIT (follow_up only): at most one follow-up phrasing per area. If
  turns_in_current_area >= 2 you MUST choose next_area — never another follow_up.
  next_area may stay on the same subject while the plan block continues; when
  turns_in_current_area >= topic_budget OR the plan slot topic differs, you MUST
  switch to that new subject (or remaining_areas).
- Do NOT wait for the candidate to say "next topic". Advance automatically.
- Cover multiple planned subjects across the interview; do not stay on one concept.
- Avoid repeating the same ask with slightly different wording.
- If the candidate cannot answer, acknowledge briefly in evaluation and move on.
- PACING (the interview is TIMED): minutes_remaining is the time budget. If
  minutes_remaining <= 5 you MUST return decision="complete" with next_question=""
  after evaluating the answer. With 25-50% of time left, start covering the most
  important remaining areas rather than deep follow-ups.
- Prefer depth on the candidate's own claimed projects (see candidate_angle_notes).
- STRICT mode: never put hints, teaching, or the correct answer in next_question.
- When last_answer is present, fill evaluation thoroughly:
  coverage, strengths, gaps (mistakes / missing concepts), expected_answer_explanation.
  For coding/DSA answers also fill corrected_code, time_complexity, space_complexity.
  Keep solutions ONLY in evaluation fields — never in next_question.
- When last_answer is null (opening question), leave evaluation lists empty and
  expected_answer_explanation / corrected_code / complexities empty.
- If questions_remaining is 0, decision MUST be complete.
- question_type is one of conceptual, behavioral, mcq, case_study, numeric,
  code_read, coding. Use preferred_format and allowed_types when they are set.
  coding ONLY when the candidate must write code. code_read puts the snippet in
  code_snippet. case_study puts a short scenario in scenario and asks one question.
  numeric asks for one number (unit and tolerance stay out of next_question).
  mcq has exactly 4 options and one correct_index; do not put the key in next_question.
  If allowed_types is absent and programming_track is false, never use coding or code_read.
- notes_for_report: 1-2 sentence evidence note for the feedback agent.
"""
)

GUIDED_QUESTION_SYSTEM_PROMPT = (
    """You are InterviewCopilot's interviewer in GUIDED mode.
"""
    + PERSONA_BLOCK
    + GUIDED_REACTION_RULE
    + SINGLE_FOCUS_RULE
    + """
"""
    + COVERAGE_RUBRIC
    + """
Rules:
- Ask ONE question at a time. Questions must be concrete and answerable in text.
- Follow the question_areas / track topics from the brief.
- QUESTION BANK: question_bank holds pre-validated questions for this track.
  STRONGLY PREFER the next unused bank question matching the current or next area,
  used VERBATIM — they are already quality-checked. Improvise only for adaptive
  follow-ups, when no suitable unused bank question remains, or when the bank
  question would be a poor fit for the answer just given.
- NEVER repeat an asked question, and NEVER ask a near-paraphrase of one in
  asked_questions (different wording of the same ask still counts as a repeat).
- Compare learning objectives: if a candidate question tests the same concepts
  as any asked_questions entry, REJECT it and pick a genuinely different concept.
- Each new question must target a DISTINCT concept or skill within the track.
  Prefer remaining_areas when non-empty; otherwise pick a new subtopic that has
  not been covered yet (see covered_areas).
- Progress difficulty with questions_asked: early foundational, later deeper.
- Stay relevant to the selected track. Do not invent unrelated domains.
- After each answer: evaluate coverage honestly. Use follow_up ONLY when coverage
  is none or partial and a genuine clarification is needed. When coverage is good
  or excellent, choose next_area and ask the next planned subject/objective —
  never a soft paraphrase of the same concept.
- Depth: aim for about topic_budget questions on the current subject before
  leaving. Use question_plan_slot.topic when present — do not ignore it.
- HARD LIMIT (follow_up only): at most one follow-up phrasing per area. If
  turns_in_current_area >= 2 you MUST choose next_area — never another follow_up.
  next_area may stay on the same subject while the plan block continues; when
  turns_in_current_area >= topic_budget OR the plan slot topic differs, you MUST
  switch to that new subject (or remaining_areas).
- Do NOT wait for the candidate to say "next topic". Advance automatically.
- Cover multiple planned subjects across the interview; do not stay on one concept.
- Avoid repeating the same ask with slightly different wording.
- If the candidate cannot answer, acknowledge briefly in evaluation and move on.
- PACING (the interview is TIMED): minutes_remaining is the time budget. If
  minutes_remaining <= 5 you MUST return decision="complete" with next_question=""
  after evaluating the answer. With 25-50% of time left, start covering the most
  important remaining areas rather than deep follow-ups.
- Prefer depth on the candidate's own claimed projects (see candidate_angle_notes).
- GUIDED mode: keep next_question conversational. Do NOT dump full answers or
  unsolicited multi-level teaching in next_question — progressive assistance is
  delivered only through the separate assistance API when the candidate asks.
- When last_answer is present, fill evaluation thoroughly:
  coverage, strengths, gaps (mistakes / missing concepts), expected_answer_explanation.
  For coding/DSA answers also fill corrected_code, time_complexity, space_complexity.
  Keep solutions ONLY in evaluation fields — never in next_question.
- When last_answer is null (opening question), leave evaluation lists empty and
  expected_answer_explanation / corrected_code / complexities empty.
- If questions_remaining is 0, decision MUST be complete.
- question_type is one of conceptual, behavioral, mcq, case_study, numeric,
  code_read, coding. Use preferred_format and allowed_types when they are set.
  coding ONLY when the candidate must write code. code_read puts the snippet in
  code_snippet. case_study puts a short scenario in scenario and asks one question.
  numeric asks for one number (unit and tolerance stay out of next_question).
  mcq has exactly 4 options and one correct_index; do not put the key in next_question.
  If allowed_types is absent and programming_track is false, never use coding or code_read.
- notes_for_report: 1-2 sentence evidence note for the feedback agent. Note if the
  candidate appeared to need coaching.
"""
)

# Backward-compatible aliases used by older imports/tests.
STRICT_SYSTEM_PROMPT = STRICT_QUESTION_SYSTEM_PROMPT
GUIDED_SYSTEM_PROMPT = GUIDED_QUESTION_SYSTEM_PROMPT
SYSTEM_PROMPT = STRICT_SYSTEM_PROMPT


def system_prompt_for_mode(mode: str, persona_id: str | None = None) -> str:
    from app.agents.persona import persona_prompt_block

    base = (
        GUIDED_QUESTION_SYSTEM_PROMPT
        if mode == "guided"
        else STRICT_QUESTION_SYSTEM_PROMPT
    )
    extra = persona_prompt_block(persona_id, mode=mode)
    if extra:
        return f"{base}\n{extra}"
    return base


class AnswerEvaluation(BaseModel):
    coverage: Literal["none", "partial", "good", "excellent"]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    expected_answer_explanation: str = ""
    corrected_code: str = ""
    time_complexity: str = ""
    space_complexity: str = ""


class QuestionMove(BaseModel):
    """Next-question fields only (evaluation is produced separately)."""

    decision: Literal["follow_up", "next_area", "complete"]
    next_question: str
    question_area: str
    question_type: Literal[
        "coding", "conceptual", "behavioral", "mcq", "code_read", "case_study", "numeric"
    ] = "conceptual"
    notes_for_report: str = ""
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = None
    option_explanation: str = ""
    code_snippet: str = ""
    objective: str = ""
    scenario: str = ""
    key_points: list[str] = Field(default_factory=list)
    expected_value: float | None = None
    unit: str = ""
    tolerance: float | None = None

    @model_validator(mode="after")
    def _question_required_unless_complete(self) -> "QuestionMove":
        if self.decision != "complete" and not self.next_question.strip():
            raise ValueError("next_question is required unless decision is complete")
        if self.decision != "complete" and not self.question_area.strip():
            raise ValueError("question_area is required unless decision is complete")
        return self


class TurnDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evaluation: AnswerEvaluation
    decision: Literal["follow_up", "next_area", "complete"]
    next_question: str
    question_area: str
    question_type: Literal[
        "coding", "conceptual", "behavioral", "mcq", "code_read", "case_study", "numeric"
    ] = "conceptual"
    notes_for_report: str = ""
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = None
    option_explanation: str = ""
    code_snippet: str = ""
    objective: str = ""
    scenario: str = ""
    key_points: list[str] = Field(default_factory=list)
    expected_value: float | None = None
    unit: str = ""
    tolerance: float | None = None
    # Persistence-only metadata (excluded from LLM schema / default dumps).
    evaluator_checks: list[str] = Field(default_factory=list, exclude=True)
    rubric_version: str = Field(default=RUBRIC_VERSION, exclude=True)
    model: str | None = Field(default=None, exclude=True)

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
    mongo_db: object  # AsyncIOMotorDatabase | None — avoid hard motor dep in TypedDict


# Kept for older imports/tests.
def _norm_question(q: str) -> str:
    return normalize_question(q)


def _empty_evaluation() -> AnswerEvaluation:
    return AnswerEvaluation(coverage="none", strengths=[], gaps=[])


def _as_turn(move: QuestionMove, evaluation: AnswerEvaluation) -> TurnDecision:
    return TurnDecision(
        evaluation=evaluation,
        decision=move.decision,
        next_question=move.next_question,
        question_area=move.question_area,
        question_type=move.question_type,
        notes_for_report=move.notes_for_report,
    )


# Strict mode: strip leading reaction sentences that reveal correctness.
_STRICT_SPOILER_RE = re.compile(
    r"\b("
    r"correct|incorrect|wrong|right answer|that's right|thats right|"
    r"not quite right|you (got|missed|nailed)|the answer is|actually the answer"
    r")\b",
    re.IGNORECASE,
)


def strip_strict_spoilers(text: str) -> str:
    """Drop leading sentences that reveal correctness; keep the real question."""
    raw = (text or "").strip()
    if not raw:
        return raw
    parts = re.split(r"(?<=[.!?])\s+", raw)
    kept: list[str] = []
    dropping = True
    for part in parts:
        if dropping and _STRICT_SPOILER_RE.search(part):
            continue
        dropping = False
        kept.append(part)
    cleaned = " ".join(kept).strip()
    return cleaned or raw


def decision_violation(decision: TurnDecision, payload: dict) -> str | None:
    """Return a human-readable violation, or None if the decision is acceptable."""
    turns_in_area = int(payload.get("turns_in_current_area") or 0)
    if decision.decision == "follow_up" and turns_in_area >= 2:
        return "follow_up not allowed when turns_in_current_area >= 2"
    if decision.decision == "follow_up" and _evaluation_coverage(decision) in (
        "good",
        "excellent",
    ):
        return "follow_up not allowed when coverage is already good/excellent"

    remaining_slots = payload.get("questions_remaining")
    if (
        remaining_slots is not None
        and int(remaining_slots) <= 0
        and decision.decision != "complete"
    ):
        return "must complete when questions_remaining is 0"

    if decision.decision != "complete":
        asked = _known_questions(payload)
        collide = duplicate_of(decision.next_question, asked)
        if collide is not None:
            return (
                "next_question repeats or closely paraphrases a previously asked "
                f"question: {collide[:120]}"
            )
        focus = question_focus_violation(decision.next_question)
        if focus:
            return focus
        if (payload.get("mode") or "").lower() == "strict":
            praise = strict_praise_violation(decision.next_question)
            if praise:
                return praise
        if decision.question_type == "mcq":
            problem = mcq_violation(decision.options, decision.correct_index)
            if problem:
                return problem
        if decision.question_type == "code_read" and not (decision.code_snippet or "").strip():
            return "code_read question is missing its snippet"
        if decision.question_type == "case_study" and len(decision.scenario.strip()) < 20:
            return "case_study question is missing its scenario"
        if decision.question_type == "numeric":
            problem = numeric_violation(decision.expected_value, decision.tolerance, decision.unit)
            if problem:
                return problem
        if not question_type_allowed(decision.question_type, payload):
            return "question type is not allowed for this subject"
    return None


def _evaluation_coverage(decision: TurnDecision) -> str:
    ev = getattr(decision, "evaluation", None)
    if ev is None:
        return ""
    return (getattr(ev, "coverage", None) or "").strip().lower()


def _planned_topic(payload: dict) -> str:
    slot = payload.get("question_plan_slot")
    if isinstance(slot, dict):
        return (slot.get("topic") or "").strip()
    return ""


def _topic_budget(payload: dict) -> int:
    raw = payload.get("topic_budget")
    try:
        return max(2, min(5, int(raw)))
    except (TypeError, ValueError):
        return 3


def _force_topic(decision: TurnDecision, topic: str) -> TurnDecision:
    return decision.model_copy(
        update={
            "decision": "next_area",
            "question_area": topic,
        }
    )


def _progression_target(payload: dict, current: str) -> str | None:
    """Best next subject: distinct planned slot, then remaining areas, else planned."""
    remaining = list(payload.get("remaining_areas") or [])
    planned = _planned_topic(payload)
    current_key = (current or "").strip().lower()
    if planned and planned.lower() != current_key:
        return planned
    for topic in remaining:
        text = (topic or "").strip()
        if text and text.lower() != current_key:
            return text
    # Scan full plan for the next different subject (resume / refresh safe).
    from app.agents.question_plan import next_distinct_plan_topic

    distinct = next_distinct_plan_topic(
        payload.get("question_plan"),
        questions_asked=int(payload.get("questions_asked") or 0),
        current=current,
    )
    if distinct:
        return distinct
    return planned or None


def apply_local_policy(decision: TurnDecision, payload: dict) -> TurnDecision:
    """Deterministic mode/policy fixes that do not require another LLM call."""
    turns_in_area = int(payload.get("turns_in_current_area") or 0)
    remaining = list(payload.get("remaining_areas") or [])
    remaining_slots = payload.get("questions_remaining")
    mode = (payload.get("mode") or "strict").lower()
    current = (payload.get("current_area") or "").strip()
    planned = _planned_topic(payload)
    budget = _topic_budget(payload)
    coverage = _evaluation_coverage(decision)

    if remaining_slots is not None and int(remaining_slots) <= 0:
        return decision.model_copy(update={"decision": "complete", "next_question": ""})

    # Sufficient answers must advance — soft follow-ups must not burn the plan.
    if decision.decision == "follow_up" and coverage in ("good", "excellent"):
        target = _progression_target(payload, current) or planned or current
        if target:
            decision = _force_topic(decision, target)
        else:
            decision = decision.model_copy(update={"decision": "next_area"})

    if decision.decision == "follow_up" and turns_in_area >= 2:
        target = _progression_target(payload, current)
        if target:
            decision = _force_topic(decision, target)
        else:
            return decision.model_copy(update={"decision": "complete", "next_question": ""})

    # Finish the subject block, then leave — do not linger indefinitely.
    if decision.decision != "complete" and current and turns_in_area >= budget:
        target = _progression_target(payload, current)
        if target:
            decision = _force_topic(decision, target)

    # Plan already advanced to a new subject — honor it once depth is underway.
    if (
        decision.decision != "complete"
        and current
        and planned
        and planned.lower() != current.lower()
        and turns_in_area >= 2
    ):
        decision = _force_topic(decision, planned)

    # next_area that stays on the same label while other subjects remain → move on.
    decided_area = (decision.question_area or "").strip()
    if (
        decision.decision == "next_area"
        and current
        and decided_area
        and decided_area.lower() == current.lower()
        and turns_in_area >= 2
    ):
        target = _progression_target(payload, current)
        if target and target.lower() != current.lower():
            decision = _force_topic(decision, target)

    if decision.decision == "complete" and not _plan_still_open(payload, remaining_slots):
        return decision.model_copy(update={"next_question": decision.next_question or ""})

    if mode == "strict" and decision.next_question:
        cleaned = strip_strict_praise(strip_strict_spoilers(decision.next_question))
        if cleaned != decision.next_question:
            decision = decision.model_copy(update={"next_question": cleaned})
    if (
        decision.decision != "complete"
        and decision.next_question
        and question_focus_violation(decision.next_question)
    ):
        repaired = repair_single_focus(decision.next_question)
        if repaired != decision.next_question and not question_focus_violation(repaired):
            decision = decision.model_copy(update={"next_question": repaired})

    # A planned slot is still waiting. Keep going instead of ending early.
    if decision.decision == "complete" and _plan_still_open(payload, remaining_slots):
        decision = decision.model_copy(
            update={
                "decision": "next_area",
                "next_question": (decision.next_question or "").strip()
                or "Continue with the next planned objective.",
                "question_area": planned
                or (decision.question_area or "").strip()
                or "General",
            }
        )
    decision = _prefer_unused_bank(decision, payload)
    if decision.decision != "complete" and decision.next_question:
        served = prepare_served_question(decision.next_question, mode=mode)
        if served and served != decision.next_question:
            decision = decision.model_copy(update={"next_question": served})
    if not question_type_allowed(decision.question_type, payload):
        decision = decision.model_copy(
            update={
                "question_type": "conceptual",
                "code_snippet": "",
                "options": [],
                "scenario": "",
            }
        )
    return decision


def _plan_still_open(payload: dict, remaining_slots) -> bool:
    planned = payload.get("question_plan_slot") or (payload.get("covered_so_far") or {}).get(
        "next_planned_objective"
    )
    return bool(planned) and remaining_slots is not None and int(remaining_slots) > 0


def _known_questions(payload: dict) -> list[str]:
    asked = [q for q in payload.get("asked_questions") or [] if q]
    prior = [q for q in payload.get("prior_track_questions") or [] if q]
    return asked + [q for q in prior if q not in asked]


def _prompt_payload(payload: dict) -> dict:
    """Cap track history before it is sent to the model. Selection still sees it all."""
    history = [str(q) for q in payload.get("prior_track_questions") or [] if q]
    areas = [str(area) for area in payload.get("prior_areas") or [] if area]
    visible = {key: value for key, value in payload.items() if key != "prior_fingerprints"}
    transcript = list(visible.get("transcript") or [])
    if len(transcript) > 6:
        visible["transcript"] = transcript[-6:]
    bank = list(visible.get("question_bank") or [])
    if len(bank) > 12:
        visible["question_bank"] = bank[:12]
    brief = visible.get("brief")
    if isinstance(brief, dict):
        brief = dict(brief)
        brief_bank = list(brief.get("question_bank") or [])
        if len(brief_bank) > 12:
            brief["question_bank"] = brief_bank[:12]
        visible["brief"] = brief
    return {
        **visible,
        "prior_areas": areas[-12:],
        "prior_track_questions": [q[:140] for q in history[-20:]],
    }


def _known_fingerprints(payload: dict) -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    for raw in payload.get("prior_fingerprints") or []:
        fingerprint = tuple(raw)
        if len(fingerprint) >= 4:
            found.add(fingerprint)
    for text in _known_questions(payload):
        fingerprint = fingerprint_tuple(text)
        if len(fingerprint) >= 4:
            found.add(fingerprint)
    return found


def _unused_bank_entries(payload: dict) -> list[dict]:
    asked = _known_questions(payload)
    fingerprints = _known_fingerprints(payload)
    unused: list[dict] = []
    for entry in payload.get("question_bank") or []:
        if not isinstance(entry, dict):
            continue
        question = (entry.get("question") or "").strip()
        if not question or is_duplicate_question(question, asked):
            continue
        fingerprint = fingerprint_tuple(question)
        if len(fingerprint) >= 4 and fingerprint in fingerprints:
            continue
        unused.append(entry)
    return unused


_BANK_TYPES = (
    "coding",
    "conceptual",
    "behavioral",
    "mcq",
    "code_read",
    "case_study",
    "numeric",
)


def _fields_from_bank(entry: dict, decision: TurnDecision) -> dict:
    qtype = entry.get("type")
    return {
        "next_question": (entry.get("question") or "").strip(),
        "question_area": (entry.get("area") or decision.question_area or "General"),
        "question_type": qtype if qtype in _BANK_TYPES else decision.question_type,
        "objective": entry.get("objective") or entry.get("area") or "",
        "options": list(entry.get("options") or []),
        "correct_index": entry.get("correct_index"),
        "option_explanation": entry.get("explanation") or entry.get("expected_answer_sketch") or "",
        "code_snippet": entry.get("code_snippet") or "",
        "scenario": entry.get("scenario") or "",
        "key_points": list(entry.get("key_points") or []),
        "expected_value": entry.get("expected_value"),
        "unit": entry.get("unit") or "",
        "tolerance": entry.get("tolerance"),
    }


def _servable_fields(entry: dict, decision: TurnDecision, mode: str) -> dict | None:
    cleaned = prepare_served_question(entry.get("question") or "", mode=mode)
    if not cleaned:
        return None
    fields = _fields_from_bank(entry, decision)
    fields["next_question"] = cleaned
    return fields


def _prefer_unused_bank(decision: TurnDecision, payload: dict) -> TurnDecision:
    """Use a validated bank question before a generated one. Dedupe still applies."""
    if decision.decision == "complete":
        return decision
    mode = (payload.get("mode") or "strict").lower()
    brief = payload.get("brief") if isinstance(payload.get("brief"), dict) else {}
    avoid = [area for area in payload.get("avoid_areas") or [] if area]
    if brief.get("pool"):
        chosen = pick_pool_question(
            [entry for entry in payload.get("question_bank") or [] if isinstance(entry, dict)],
            seed=str((payload.get("meta") or {}).get("session_id") or "session"),
            slot=payload.get("question_plan_slot")
            if isinstance(payload.get("question_plan_slot"), dict)
            else None,
            asked=[q for q in payload.get("asked_questions") or [] if q],
            history=[q for q in payload.get("prior_track_questions") or [] if q],
            covered_areas=list(payload.get("covered_areas") or []),
            mode=mode,
            fingerprints=[tuple(fp) for fp in payload.get("prior_fingerprints") or []],
            avoid_areas=avoid,
            reuse=False,
        )
        if chosen:
            return decision.model_copy(update=_fields_from_bank(chosen, decision))
        return decision
    unused = _unused_bank_entries(payload)
    if avoid:
        steered = [entry for entry in unused if (entry.get("area") or "") not in set(avoid)]
        if steered:
            unused = steered
    planned = _planned_topic(payload).lower()
    if planned:
        on_topic = [
            entry
            for entry in unused
            if (entry.get("area") or "").strip().lower() == planned
        ]
        if on_topic:
            unused = on_topic
    if not unused:
        return decision
    current = (decision.next_question or "").strip()
    if current:
        for entry in unused:
            question = (entry.get("question") or "").strip()
            if question and is_duplicate_question(current, [question]):
                fields = _servable_fields(entry, decision, mode)
                if fields:
                    return decision.model_copy(update=fields)
    for entry in unused:
        fields = _servable_fields(entry, decision, mode)
        if fields:
            return decision.model_copy(update=fields)
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
    asked = _known_questions(payload)
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

    # M9: unused validated bank questions come FIRST.
    for entry in payload.get("question_bank") or []:
        q = (entry.get("question") or "").strip()
        if q and not any(is_duplicate_question(q, [a]) for a in asked):
            candidates.append(q)

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


def _has_answer(payload: dict) -> bool:
    answer = payload.get("last_answer")
    return bool(answer is not None and str(answer).strip())


def _looks_like_code_answer(payload: dict, answer: str) -> bool:
    qtype = (payload.get("open_question_type") or "").lower()
    if qtype == "coding":
        return True
    blob = f"{payload.get('last_question') or ''}\n{answer}".lower()
    return any(
        token in blob
        for token in ("```", "def ", "class ", "public static", "#include", "time complexity")
    )


def evaluation_inconsistencies(ev: AnswerEvaluation, *, is_code: bool) -> list[str]:
    """Return check ids for inconsistent evaluation shapes."""
    issues: list[str] = []
    if ev.coverage in ("excellent", "good") and not ev.strengths:
        issues.append("high_label_without_strengths")
    if ev.coverage == "none" and ev.strengths:
        issues.append("none_with_strengths")
    if ev.coverage in ("none", "partial") and not [g for g in ev.gaps if str(g).strip()]:
        issues.append("low_label_without_gaps")
    # Fields must exist (schema) and be strings — empty string is explicit.
    if is_code and (ev.time_complexity is None or ev.space_complexity is None):
        issues.append("code_missing_complexity_fields")
    return issues


def _safe_eval_fallback(ev: AnswerEvaluation, issues: list[str]) -> AnswerEvaluation:
    """Deterministic repair when the LLM stays inconsistent after one retry."""
    strengths = list(ev.strengths)
    gaps = list(ev.gaps)
    coverage = ev.coverage
    if "high_label_without_strengths" in issues:
        coverage = "partial"
        if not gaps:
            gaps = ["Important details were incomplete or unclear."]
    if "none_with_strengths" in issues:
        strengths = []
    if "low_label_without_gaps" in issues and not gaps:
        gaps = [_FIXED_NONE_GAP]
    if coverage == "none" and not gaps:
        gaps = [_FIXED_NONE_GAP]
    return ev.model_copy(update={"coverage": coverage, "strengths": strengths, "gaps": gaps})


def _guarded_none_evaluation(*, check: str) -> tuple[AnswerEvaluation, list[str]]:
    ev = AnswerEvaluation(
        coverage="none",
        strengths=[],
        gaps=[_FIXED_NONE_GAP],
        expected_answer_explanation="",
    )
    return ev, [check]


async def evaluate_answer(payload: dict) -> AnswerEvaluation:
    """Score the candidate answer (guards + temp=0 LLM + consistency checks)."""
    evaluation, _checks = await evaluate_answer_with_meta(payload)
    return evaluation


async def evaluate_answer_with_meta(payload: dict) -> tuple[AnswerEvaluation, list[str]]:
    """Evaluate with cheap guards, temp=0 LLM, consistency repair, then fallback."""
    raw = payload.get("last_answer")
    text = "" if raw is None else str(raw).strip()
    checks: list[str] = []

    if not text:
        return _guarded_none_evaluation(check="empty_answer")
    if _IDK_RE.match(text):
        return _guarded_none_evaluation(check="idk_answer")
    min_chars = int(get_settings().eval_min_answer_chars)
    if len(text) < min_chars:
        return _guarded_none_evaluation(check="too_short_answer")

    is_code = _looks_like_code_answer(payload, text)
    mode = payload.get("mode") or "strict"
    eval_payload = {
        "mode": mode,
        "brief": payload.get("brief"),
        "last_question": payload.get("last_question"),
        "last_answer": text,
        "question_area": (payload.get("transcript") or [{}])[-1].get("area")
        if payload.get("transcript")
        else None,
        "is_code_answer": is_code,
        "rubric_version": RUBRIC_VERSION,
        "key_points": payload.get("key_points") or [],
        "probe_context": payload.get("probe_context") or "",
        "probe_origin": payload.get("probe_origin") or "",
    }

    system = EVALUATE_SYSTEM_PROMPT
    if is_code:
        system = f"{EVALUATE_SYSTEM_PROMPT}\n{CODING_STATIC_REVIEW_RULES}"

    ev = await structured_completion(
        system=system,
        user_payload=eval_payload,
        schema=AnswerEvaluation,
        model=payload.get("model") or "structured-json",
        temperature=0,
        max_tokens=500,
        repair_attempts=1,
        max_attempts=1,
        timeout_s=18.0,
    )
    issues = evaluation_inconsistencies(ev, is_code=is_code)
    if not issues:
        return ev, checks

    checks.extend(issues)
    repair_payload = {
        **eval_payload,
        "repair_note": (
            "Your previous evaluation was inconsistent: "
            f"{', '.join(issues)}. Fix strengths/gaps to match the coverage "
            "label. Return valid JSON only."
        ),
    }
    try:
        ev = await structured_completion(
            system=system,
            user_payload=repair_payload,
            schema=AnswerEvaluation,
            temperature=0,
            max_tokens=500,
            repair_attempts=1,
            max_attempts=1,
            timeout_s=14.0,
        )
    except Exception as exc:
        log.warning("eval_repair_failed", error=str(exc)[:160])
        checks.append("repair_failed")
        return _safe_eval_fallback(ev, issues), checks

    issues2 = evaluation_inconsistencies(ev, is_code=is_code)
    if issues2:
        checks.append("fallback_after_repair")
        checks.extend(issues2)
        return _safe_eval_fallback(ev, issues2), checks
    checks.append("repaired")
    return ev, checks


async def run_interviewer_turn(
    *,
    payload: dict,
    meta: dict | None = None,
    mongo_db: object = None,  # AsyncIOMotorDatabase | None
) -> TurnDecision:
    """Evaluate candidate answer and generate next question in a single LLM call.

    Avoids sequential 2-call latency overhead while enforcing deterministic guards
    for empty, idk, or too-short answers.
    """
    mode = payload.get("mode") or "strict"
    if mode not in ("strict", "guided"):
        mode = "strict"
    routed = {**payload, "mode": mode}
    system = system_prompt_for_mode(mode, payload.get("persona_id"))

    raw_answer = payload.get("last_answer")
    text_answer = "" if raw_answer is None else str(raw_answer).strip()
    is_idk = bool(text_answer and _IDK_RE.match(text_answer))
    min_chars = int(get_settings().eval_min_answer_chars)
    is_too_short = bool(text_answer and len(text_answer) < min_chars)

    is_code = bool(text_answer and _looks_like_code_answer(payload, text_answer))
    if is_code:
        system = f"{system}\n{CODING_STATIC_REVIEW_RULES}"

    def _apply_eval_guards(d: TurnDecision) -> TurnDecision:
        if not text_answer:
            return d.model_copy(
                update={
                    "evaluation": _empty_evaluation(),
                    "evaluator_checks": ["empty_answer"],
                    "rubric_version": RUBRIC_VERSION,
                }
            )
        if is_idk:
            ev, checks = _guarded_none_evaluation(check="idk_answer")
            return d.model_copy(
                update={
                    "evaluation": ev,
                    "evaluator_checks": checks,
                    "rubric_version": RUBRIC_VERSION,
                }
            )
        if is_too_short:
            ev, checks = _guarded_none_evaluation(check="too_short_answer")
            return d.model_copy(
                update={
                    "evaluation": ev,
                    "evaluator_checks": checks,
                    "rubric_version": RUBRIC_VERSION,
                }
            )
        return d.model_copy(update={"rubric_version": RUBRIC_VERSION})

    turn_started = time.monotonic()
    decision = await structured_completion(
        system=system,
        user_payload=_prompt_payload(routed),
        schema=TurnDecision,
        meta=meta,
        mongo_db=mongo_db,
        max_tokens=800,
        max_attempts=1,
        repair_attempts=1,
        timeout_s=22.0,
    )
    decision = _apply_eval_guards(decision)
    decision = apply_local_policy(decision, routed)
    violation = decision_violation(decision, routed)
    if violation is None:
        log.info(
            "interviewer_turn_timing",
            stage="ok",
            elapsed_ms=int((time.monotonic() - turn_started) * 1000),
        )
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
            system=system,
            user_payload=_prompt_payload(repair_payload),
            schema=TurnDecision,
            mongo_db=mongo_db,
            max_tokens=700,
            max_attempts=1,
            repair_attempts=1,
            timeout_s=16.0,
        )
        decision = _apply_eval_guards(decision)
        decision = apply_local_policy(decision, routed)
        violation = decision_violation(decision, routed)
        if violation is None:
            log.info(
                "interviewer_turn_timing",
                stage="repaired",
                elapsed_ms=int((time.monotonic() - turn_started) * 1000),
            )
            return decision

    log.warning(
        "interviewer_force_unique_after_repairs",
        violation=violation,
        asked=len(routed.get("asked_questions") or []),
        elapsed_ms=int((time.monotonic() - turn_started) * 1000),
    )
    forced = force_unique_decision(decision, routed)
    if forced.decision != "complete" and decision_violation(forced, routed):
        reused = least_recent_text(
            [q for q in routed.get("prior_track_questions") or [] if q],
            [q for q in routed.get("asked_questions") or [] if q],
        )
        if reused:
            return forced.model_copy(update={"decision": "next_area", "next_question": reused})
        return forced.model_copy(update={"decision": "complete", "next_question": ""})
    return forced


def build_interviewer_graph(turn_runner=run_interviewer_turn):
    async def evaluate(state: InterviewerState) -> dict:
        decision = await turn_runner(
            payload=state["payload"],
            mongo_db=state.get("mongo_db"),
        )
        dumped = decision.model_dump()
        # ContextVar set inside the gateway does not survive LangGraph's copy.
        # Carry the alias out on the decision payload instead.
        used = llm_model_used.get()
        if used:
            dumped["model"] = used
        return {"decision": dumped}

    graph = StateGraph(InterviewerState)
    graph.add_node("evaluate", evaluate)
    graph.add_edge(START, "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()
