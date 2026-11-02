# InterviewCopilot M5 — Interview Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Interviewer Agent — agent #3 of 4 — runs full Strict-mode text interviews: first question from the Interview Brief, adaptive follow-ups bounded per area, completion, and DB-native recovery of in-progress sessions after a backend restart.

**Architecture:** `interview_sessions` and `session_turns` in Postgres are the authoritative session state (a turn row exists the moment a question is asked; the answer fills it in). Recovery is DB-native: `GET /sessions/{id}` rebuilds everything from rows, so a crash loses nothing. **Deviation from spec §8:** instead of a LangGraph Postgres checkpointer, state lives in the domain tables directly — double persistence would add failure modes without adding guarantees. Recorded in the spec. The Interviewer graph is a LangGraph `StateGraph` with an `evaluate` node calling `structured_completion` (turn-runner injection per M3/M4 pattern). Strict mode only; Guided hint ladder arrives with M6 progression.

**Tech Stack:** Existing stack (no new dependencies). `interview_max_turns: int = 12` added to Settings.

**Spec:** `docs/superpowers/specs/2026-11-02-interviewcopilot-v1-build-design.md` (M5 row of §14)

## Global Constraints

- Same as M1–M4. Tests hit `interviewcopilot_test`; migrate BOTH DBs.
- All routes require auth; sessions are ownership-checked (404 for other users').
- LLM only via `structured_completion`; mode `interview-chat` is NOT used here — decisions are structured.

---

### Task 1: InterviewSession + SessionTurn models and migration

**Files:**
- Create: `backend/app/models/interview.py`
- Modify: `backend/alembic/env.py`, `backend/tests/conftest.py` (cleanup order)
- Test: `backend/tests/test_interview_models.py`

**Interfaces:**
- Produces: `app.models.interview.InterviewSession` — `id`, `track_id` (FK tracks CASCADE), `user_id` (FK users CASCADE, index), `mode: str` (`strict`|`guided`), `status: str` (`in_progress`|`completed`|`aborted`), timestamps, `completed_at: datetime | None`; `app.models.interview.SessionTurn` — `id`, `session_id` (FK CASCADE, index), `turn_index: int`, `question_area: str`, `question: Text`, `answer: Text | None`, `asked_at`, `answered_at: datetime | None`.
- Migration runs for dev AND test DBs.

- [ ] **Step 1: Failing test** (`backend/tests/test_interview_models.py`)

```python
import uuid

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import Track
from app.models.user import User


@pytest.mark.asyncio
async def test_session_with_turns(clean_users_table):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"i-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        session.add(track)
        await session.commit()
        await session.refresh(track)

        s = InterviewSession(track_id=track.id, user_id=user.id, mode="strict")
        session.add(s)
        await session.commit()
        await session.refresh(s)

        session.add(
            SessionTurn(
                session_id=s.id, turn_index=1, question_area="Arrays",
                question="Explain how you would find duplicates.",
            )
        )
        await session.commit()
        assert s.status == "in_progress"
```

- [ ] **Step 2: Verify fail → implement model + migration (both DBs) → verify pass → commit**

Model:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(16), default="strict")
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SessionTurn(Base):
    __tablename__ = "session_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer)
    question_area: Mapped[str] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

alembic/env.py import; autogenerate `create interview sessions and turns`; upgrade dev + test DBs; conftest cleanup adds `delete(SessionTurn)`, `delete(InterviewSession)` before tracks.

Commit: `feat(backend): interview session and turn models`.

---

### Task 2: Interviewer Agent + interview service + session routes

**Files:**
- Create: `backend/app/agents/interviewer.py`, `backend/app/services/interview_service.py`, `backend/app/api/v1/interviews.py`
- Modify: `backend/app/main.py`, `backend/app/core/config.py` (`interview_max_turns: int = 12`)
- Test: `backend/tests/test_interview.py`

**Interfaces:**
- `app.agents.interviewer.TurnDecision` (pydantic): `evaluation: {coverage: Literal["none","partial","good","excellent"], strengths: list[str], gaps: list[str]}`, `decision: Literal["follow_up","next_area","complete"]`, `next_question: str`, `question_area: str`, `notes_for_report: str = ""`.
- `build_interviewer_graph(turn_runner=...)` — node `evaluate`.
- `app.services.interview_service.start_session(db, user, track_id, mode="strict") -> dict` (404 if track/brief missing → HTTPException raised by route layer; returns `{session, turn}`), `submit_answer(db, mongo_unused, user, session_id, answer) -> dict` (`{completed: bool, evaluation, turn?}`), `get_session(db, user, session_id) -> dict | None`, `complete_session(db, user, session_id) -> dict`.
- Routes: `POST /api/v1/tracks/{track_id}/sessions` (201), `GET /api/v1/sessions/{session_id}`, `POST /api/v1/sessions/{session_id}/turns` `{answer}`, `POST /api/v1/sessions/{session_id}/complete`.
- Rules: max turns from Settings; `follow_up` allowed at most once per area (tracked by counting turns per area); completing sets `status=completed` + `completed_at`.

- [ ] **Step 1: Failing tests** (`backend/tests/test_interview.py`) — create session via `POST /tracks/{id}/sessions` with patched `run_interviewer_turn` returning a first question; submit answer leading to `next_area`; second answer leading to `complete`; `GET /sessions/{id}` shows transcript; **recovery test**: new `create_app()` instance + fresh request returns same turns; auth + 404 edges.

```python
import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.track import InterviewBrief, Track
from app.models.user import User


async def _setup_track_with_brief(monkeypatch) -> tuple[User, str, uuid.UUID, callable]:
    from app.agents.interviewer import TurnDecision

    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"iv-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="DSA")
        session.add(track)
        await session.commit()
        await session.refresh(track)
        session.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "DSA basics",
                    "competencies": [{"name": "Arrays", "description": "arrays", "importance": "core"}],
                    "question_areas": [
                        {"topic": "Hashmaps", "guidance": "collisions"},
                        {"topic": "Big-O", "guidance": "complexity analysis"},
                    ],
                },
            )
        )
        await session.commit()
    token = create_access_token(str(user.id))

    async def fake_turn(*args, **kwargs):
        payload = kwargs.get("payload") or (args[1] if args else {})
        last = payload.get("last_question")
        if not last:
            return TurnDecision(
                evaluation={"coverage": "none", "strengths": [], "gaps": []},
                decision="next_area",
                next_question="Explain hashmaps and collisions.",
                question_area="Hashmaps",
            )
        if payload.get("turns_in_area", 0) >= 1:
            return TurnDecision(
                evaluation={"coverage": "good", "strengths": ["clear"], "gaps": []},
                decision="next_area",
                next_question="What is Big-O of a hashmap lookup?",
                question_area="Big-O",
            )
        return TurnDecision(
            evaluation={"coverage": "partial", "strengths": ["ok"], "gaps": ["collisions"]},
            decision="follow_up",
            next_question="How would you handle collisions?",
            question_area="Hashmaps",
        )

    monkeypatch.setattr("app.services.interview_service.run_interviewer_turn", fake_turn)
    return user, token, track.id, fake_turn


@pytest.mark.asyncio
async def test_full_strict_interview_flow(monkeypatch, clean_users_table):
    user, token, track_id, _ = await _setup_track_with_brief(monkeypatch)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token}
        )
        assert r.status_code == 201
        sid = r.json()["session"]["id"]
        assert r.json()["turn"]["question"].startswith("Explain hashmaps")

        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "A hashmap maps keys to buckets..."},
            cookies={"ic_access": token},
        )
        assert r.json()["completed"] is False
        assert r.json()["turn"]["question"].startswith("How would you handle")

        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "Chaining or open addressing..."},
            cookies={"ic_access": token},
        )
        assert r.json()["completed"] is False
        assert r.json()["turn"]["question"].startswith("What is Big-O")

        r = await client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "O(1) average case..."},
            cookies={"ic_access": token},
        )
        assert r.json()["completed"] is True

        r = await client.get(f"/api/v1/sessions/{sid}", cookies={"ic_access": token})
        body = r.json()
        assert body["session"]["status"] == "completed"
        assert len(body["turns"]) == 3
        assert body["turns"][0]["answer"] == "A hashmap maps keys to buckets..."


@pytest.mark.asyncio
async def test_session_recovers_after_restart(monkeypatch, clean_users_table):
    user, token, track_id, _ = await _setup_track_with_brief(monkeypatch)
    app1 = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app1), base_url="http://t") as c:
        r = await c.post(f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token})
        sid = r.json()["session"]["id"]
        await c.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"answer": "buckets and hashing"},
            cookies={"ic_access": token},
        )
    app2 = create_app()  # "restart"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://t") as c:
        r = await c.get(f"/api/v1/sessions/{sid}", cookies={"ic_access": token})
        assert r.status_code == 200
        body = r.json()
        assert len(body["turns"]) == 1 and body["turns"][0]["answer"] == "buckets and hashing"
        assert body["session"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_sessions_require_auth():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/v1/sessions/{uuid.uuid4()}")
    assert r.status_code == 401
```

- [ ] **Step 2: Verify fail → implement → verify pass → commit**

`app/agents/interviewer.py`:

```python
import httpx
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.gateway.structured import structured_completion

SYSTEM_PROMPT = """You are InterviewCopilot's interviewer conducting a STRICT interview.

Rules:
- Ask ONE question at a time. Questions must be concrete and answerable in text.
- Follow the question_areas from the brief. Do not repeat questions already asked.
- After each answer: evaluate coverage honestly, then either ask ONE follow-up probing
  a gap (only if the area has not had a follow-up yet), move to the next area, or
  decide the interview is complete.
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
```

`app/services/interview_service.py` core logic:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.interviewer import build_interviewer_graph
from app.core.config import get_settings
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import Track
from app.models.user import User
from app.services.track_service import get_track_with_brief


async def run_interviewer_turn(**kwargs):
    from app.agents.interviewer import run_interviewer_turn as _run

    return await _run(**kwargs)


def _graph():
    return build_interviewer_graph(turn_runner=run_interviewer_turn)


async def start_session(db, user, track_id, mode="strict") -> dict:
    track_brief = await get_track_with_brief(db, user, track_id)
    if track_brief is None:
        raise LookupError("track_not_found")
    if track_brief["brief"] is None:
        raise LookupError("brief_not_found")

    session = InterviewSession(track_id=track_id, user_id=user.id, mode=mode)
    db.add(session)
    await db.commit()
    await db.refresh(session)

    decision = await _decide(db, session, track_brief["brief"]["content"], last_answer=None)
    turn = await _append_turn(db, session, decision, first=True)
    return {"session": _session_dict(session), "turn": _turn_dict(turn)}


async def submit_answer(db, user, session_id, answer: str) -> dict:
    session = await _owned_session(db, user, session_id)
    last_turn = await _latest_turn(db, session.id)
    if last_turn is None or last_turn.answer is not None:
        raise LookupError("no_open_question")
    last_turn.answer = answer
    last_turn.answered_at = datetime.now(timezone.utc)
    await db.commit()

    track_brief = await get_track_with_brief(db, user, session.track_id)
    decision = await _decide(db, session, track_brief["brief"]["content"], last_answer=answer)

    turns_so_far = await _count_turns(db, session.id)
    max_turns = get_settings().interview_max_turns
    if decision.decision == "complete" or turns_so_far >= max_turns:
        await _complete(session)
        return {"completed": True, "evaluation": decision.evaluation.model_dump()}

    turn = await _append_turn(db, session, decision, first=False)
    return {"completed": False, "evaluation": decision.evaluation.model_dump(), "turn": _turn_dict(turn)}


async def _decide(db, session, brief_content, *, last_answer):
    turns = await _turns(db, session.id)
    last_question = turns[-1].question if turns else None
    turns_in_area = sum(1 for t in turns if t.question_area == (turns[-1].question_area if turns else None))
    payload = {
        "brief": brief_content,
        "transcript": [
            {"question": t.question, "answer": t.answer, "area": t.question_area} for t in turns
        ],
        "last_question": last_question,
        "last_answer": last_answer,
        "turns_in_current_area": turns_in_area,
        "questions_asked": len(turns),
    }
    result = await _graph().ainvoke({"payload": payload})
    return TurnDecision.model_validate(result["decision"])


async def _append_turn(db, session, decision, *, first):
    index = (await _count_turns(db, session.id)) + 1
    turn = SessionTurn(
        session_id=session.id,
        turn_index=index,
        question_area=decision.question_area,
        question=decision.next_question,
    )
    db.add(turn)
    await db.commit()
    await db.refresh(turn)
    return turn


async def _owned_session(db, user, session_id) -> InterviewSession:
    s = await db.get(InterviewSession, session_id)
    if s is None or s.user_id != user.id:
        raise LookupError("session_not_found")
    return s


async def _turns(db, session_id):
    result = await db.execute(
        select(SessionTurn).where(SessionTurn.session_id == session_id).order_by(SessionTurn.turn_index)
    )
    return list(result.scalars().all())


async def _count_turns(db, session_id) -> int:
    return len(await _turns(db, session_id))


async def _complete(session):
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    await db.commit()


def _session_dict(s):
    return {"id": str(s.id), "track_id": str(s.track_id), "mode": s.mode, "status": s.status}


def _turn_dict(t):
    return {
        "turn_index": t.turn_index,
        "question_area": t.question_area,
        "question": t.question,
        "answer": t.answer,
    }
```

Routes translate `LookupError` to 404/409; `get_session` returns `{session, turns}` and `complete_session` aborts. `main.py` registers the router.

- [ ] **Step 3: Run tests → all pass → commit** `feat(backend): interviewer agent (langgraph) with strict interview engine`

---

### Task 3: README, live strict interview, push

- [ ] Append M5 section to README (start session / answer turns / get transcript curls).
- [ ] Full suite + lint; **live acceptance**: real LLM strict interview against the M4 track — start session, answer 3 turns honestly, verify completion + transcript.
- [ ] Record the checkpointer deviation in the spec (§8 note), commit, push.

---

## M5 Acceptance (from spec §14)

- [ ] Full Strict text interview with adaptive follow-ups (real LLM)
- [ ] Turns persisted; session recovers after backend restart (new app instance sees full state)
- [ ] Suite green; pushed
