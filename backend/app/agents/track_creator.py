import asyncio
from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.gateway.structured import structured_completion

log = get_logger(__name__)

# Free-tier TPM windows: pipeline LLM calls are spaced out. Tests patch to 0.
BANK_CALL_SPACING_S = 5

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


class BankQuestion(BaseModel):
    area: str
    question: str
    difficulty: Literal["foundational", "intermediate", "advanced"]
    type: Literal["coding", "conceptual", "behavioral"]
    expected_answer_sketch: str = ""


class InterviewBriefContent(BaseModel):
    summary: str
    preparation_plan: list[str] = Field(default_factory=list)
    competencies: list[Competency] = Field(default_factory=list)
    question_areas: list[QuestionArea] = Field(default_factory=list)
    candidate_angle_notes: str = ""
    question_bank: list[BankQuestion] = Field(default_factory=list)


class TrackCreatorState(TypedDict, total=False):
    objective: dict
    vault_summary: list[dict]
    brief: dict
    bank: list


BANK_SYSTEM_PROMPT = """You are InterviewCopilot's question bank author. Given an
interview brief (areas, competencies, candidate angle), write 3-5 ANCHOR questions for
this track. These are the opening questions of timed interview sessions — the interviewer
generates all follow-up questions itself from the candidate's answers.

Rules:
- 3-5 questions ONLY, each testing a DIFFERENT learning objective, spread across the
  brief's question_areas.
- Difficulty arc: start foundational, end advanced.
- Every question must be self-contained and answerable in plain text.
- Mark type: coding (write/fix code), conceptual (explain/compare), or behavioral.
- expected_answer_sketch: ONE sentence (max ~120 chars) on what a strong answer covers.
- Ground questions in the candidate's context where the brief's candidate_angle_notes
  suggests it.
"""

JUDGE_SYSTEM_PROMPT = """You are InterviewCopilot's question quality judge. For each
indexed question, decide accept/reject.

Reject a question when ANY of these hold:
- vague, ambiguous, or unanswerable in text;
- trivially shallow for an interview (yes/no with no reasoning);
- tests the same learning objective as another accepted question;
- out of scope for the track subject.
Give a short actionable reason for every rejection.
"""


class BankJudgeItem(BaseModel):
    index: int
    accept: bool
    reason: str = ""


class BankJudgeVerdict(BaseModel):
    # Typed so a shape mismatch (e.g. model answers "verdict" instead of
    # "accept") triggers structured_completion's repair loop instead of
    # silently rejecting every question.
    verdicts: list[BankJudgeItem] = Field(default_factory=list)


async def run_track_creator_turn(
    *, objective: dict, vault_summary: list[dict], meta: dict | None = None
) -> InterviewBriefContent:
    payload = {"candidate_vault": vault_summary, "track_objective": objective}
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        return await structured_completion(
            client,
            system=SYSTEM_PROMPT,
            user_payload=payload,
            schema=InterviewBriefContent,
            meta=meta,
        )


async def run_bank_builder_turn(
    *,
    objective: dict,
    brief: dict,
    regenerate_indices: list[int] | None = None,
    meta: dict | None = None,
) -> list[BankQuestion]:
    payload = {
        "track_objective": objective,
        # Trim: only what authoring needs (full brief blows free-tier TPM limits).
        "brief": {
            "summary": brief.get("summary", ""),
            "question_areas": brief.get("question_areas", []),
            "candidate_angle_notes": brief.get("candidate_angle_notes", ""),
        },
        "target_count": 4,
    }
    system = BANK_SYSTEM_PROMPT
    if regenerate_indices:
        payload["regenerate_only_these_indices"] = regenerate_indices
        system += (
            "\nREGENERATION MODE: produce replacements ONLY for the listed indices of the "
            "previously rejected questions. Fix every stated rejection reason. Return the "
            "replacement questions as a plain JSON array under key 'questions'."
        )
        schema = _BankRegeneration
    else:
        schema = _BankGeneration

    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        result = await structured_completion(
            client, system=system, user_payload=payload, schema=schema, meta=meta
        )
    return result.questions


async def run_bank_judge_turn(
    *, objective: dict, questions: list[dict], meta: dict | None = None
) -> BankJudgeVerdict:
    payload = {"track_objective": objective, "questions": questions}
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        return await structured_completion(
            client,
            system=JUDGE_SYSTEM_PROMPT,
            user_payload=payload,
            schema=BankJudgeVerdict,
            meta=meta,
        )


class _BankQuestionIn(BaseModel):
    area: str = ""
    question: str
    difficulty: Literal["foundational", "intermediate", "advanced"] = "intermediate"
    type: Literal["coding", "conceptual", "behavioral"] = "conceptual"
    expected_answer_sketch: str = ""


class _BankGeneration(BaseModel):
    questions: list[_BankQuestionIn] = Field(default_factory=list)


class _BankRegeneration(BaseModel):
    questions: list[_BankQuestionIn] = Field(default_factory=list)


def build_track_creator_graph(
    turn_runner=run_track_creator_turn,
    bank_runner=run_bank_builder_turn,
    judge_runner=run_bank_judge_turn,
    regen_runner=None,
):
    async def author(state: TrackCreatorState) -> dict:
        content = await turn_runner(
            objective=state["objective"],
            vault_summary=state.get("vault_summary", []),
            meta=state.get("meta") or None,
        )
        return {"brief": content.model_dump()}

    async def build_bank(state: TrackCreatorState) -> dict:
        from app.agents.question_dedupe import is_duplicate_question

        brief = state["brief"]
        objective = state["objective"]
        regen = regen_runner or bank_runner
        bank: list[dict] = []
        try:
            # Free-tier TPM windows: space the pipeline's calls out instead of
            # bursting (author just fired moments ago).
            await asyncio.sleep(BANK_CALL_SPACING_S)
            questions = await bank_runner(
                objective=objective, brief=brief, meta=state.get("meta") or None
            )
            bank = [q.model_dump() for q in questions]
        except Exception as exc:
            log.warning("bank_generation_failed", error=str(exc))
            return {"brief": {**brief, "question_bank": []}}

        # Bounded validation loop (audit-proof structure): accepted questions are
        # FINAL and never re-judged; each round validates only new candidates;
        # one regeneration round for rejects; bank always ships.
        all_accepted: list[dict] = []
        pending: list[dict] = bank
        try:
            for round_no in range(2):
                # Dedupe within candidates and against everything accepted so far.
                candidates: list[dict] = []
                rejects: list[tuple[dict, str]] = []
                for q in pending:
                    text = q.get("question", "")
                    against = [a.get("question", "") for a in all_accepted] + [
                        c.get("question", "") for c in candidates
                    ]
                    if not text or (
                        against and any(is_duplicate_question(text, [s]) for s in against)
                    ):
                        rejects.append((q, "duplicates an earlier bank question"))
                        continue
                    candidates.append(q)

                if not candidates:
                    break

                judged_idx: set[int] = set()
                try:
                    await asyncio.sleep(BANK_CALL_SPACING_S)
                    verdict = await judge_runner(
                        objective=objective,
                        questions=[{**q, "index": i} for i, q in enumerate(candidates)],
                        meta=state.get("meta") or None,
                    )
                    for v in verdict.verdicts:
                        idx = v.index
                        if not (0 <= idx < len(candidates)):
                            continue
                        judged_idx.add(idx)
                        if v.accept:
                            all_accepted.append(candidates[idx])
                        else:
                            rejects.append((candidates[idx], v.reason or "rejected"))
                except Exception as exc:
                    log.warning("bank_judge_failed", error=str(exc))

                # Un-judged candidates are kept (never silently dropped).
                for i, q in enumerate(candidates):
                    if i not in judged_idx:
                        all_accepted.append(q)

                if not rejects or round_no == 1:
                    log.info("bank_built", accepted=len(all_accepted), rejected=len(rejects))
                    break

                # One regeneration round: replace ONLY the rejected questions.
                try:
                    questions = await regen(
                        objective=objective,
                        brief=brief,
                        regenerate_indices=list(range(len(rejects))),
                        meta=state.get("meta") or None,
                    )
                    pending = [q.model_dump() for q in questions]
                except Exception as exc:
                    log.warning("bank_regeneration_failed", error=str(exc))
                    break
        except Exception as exc:
            log.warning("bank_validation_failed", error=str(exc))

        return {"brief": {**brief, "question_bank": all_accepted}}

    graph = StateGraph(TrackCreatorState)
    graph.add_node("author", author)
    graph.add_node("build_bank", build_bank)
    graph.add_edge(START, "author")
    graph.add_edge("author", "build_bank")
    graph.add_edge("build_bank", END)
    return graph.compile()
