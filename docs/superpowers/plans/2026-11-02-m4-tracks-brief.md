# InterviewCopilot M4 — Tracks & Interview Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Track Creator Agent — agent #2 of 4 — turns a preparation objective (topic / role / company+JD) plus the candidate vault into a versioned Interview Brief that later agents (Interviewer M5, Feedback M6) will consume.

**Architecture:** `tracks` and `interview_briefs` (versioned JSONB content, one row per version) in Postgres. The agent is a LangGraph `StateGraph` with a single authoring node calling `structured_completion`; the injectable-turn-runner pattern from M3 is reused so tests patch the service-module indirection. Company research uses only the supplied JD text (web research is out of scope for v1, spec §16).

**Tech Stack:** Existing stack (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-11-02-interviewcopilot-v1-build-design.md` (M4 row of §14)

## Global Constraints

- Same as M1–M3 (Python 3.13 + uv, Git Bash, conventional commits, secrets in root `.env`).
- Tests run against `interviewcopilot_test` (conftest env override) — real DB untouchable.
- New tables must be migrated in BOTH databases: `alembic upgrade head` for dev, and with the `DATABASE_URL=...interviewcopilot_test` override for tests.
- All routes require auth (`get_current_user`).

---

### Task 1: Track + InterviewBrief models and migration

**Files:**
- Create: `backend/app/models/track.py`
- Modify: `backend/alembic/env.py` (register tables)
- Create: migration via autogenerate (dev + test DBs)
- Modify: `backend/tests/conftest.py` (cleanup also clears tracks/briefs)
- Test: `backend/tests/test_track_models.py`

**Interfaces:**
- Consumes: `Base`, `get_db`.
- Produces:
  - `app.models.track.Track` — `id`, `user_id` (FK CASCADE), `track_type: str` (`topic`|`role`|`company_jd`), `subject: str`, `company: str | None`, `jd_text: str | None` (Text), `status: str` default `active`, timestamps.
  - `app.models.track.InterviewBrief` — `id`, `track_id` (FK tracks CASCADE, index), `version: int`, `content: dict` (JSONB), `created_at`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_track_models.py`:

```python
import uuid

import pytest

from app.db.sqlalchemy import SessionFactory
from app.models.track import InterviewBrief, Track
from app.models.user import User


@pytest.mark.asyncio
async def test_track_with_versioned_briefs(clean_users_table):
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"t-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        track = Track(
            user_id=user.id, track_type="topic", subject="Data Structures & Algorithms"
        )
        session.add(track)
        await session.commit()
        await session.refresh(track)

        session.add(InterviewBrief(track_id=track.id, version=1, content={"summary": "v1"}))
        await session.commit()
        session.add(InterviewBrief(track_id=track.id, version=2, content={"summary": "v2"}))
        await session.commit()

        briefs = (
            (
                await session.execute(
                    InterviewBrief.__table__.select().where(InterviewBrief.track_id == track.id)
                )
            )
            .mappings()
            .all()
        )
        assert [b["version"] for b in briefs] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_track_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.track'`.

- [ ] **Step 3: Implement**

Create `backend/app/models/track.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    track_type: Mapped[str] = mapped_column(String(16))  # topic | role | company_jd
    subject: Mapped[str] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InterviewBrief(Base):
    __tablename__ = "interview_briefs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracks.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[int] = mapped_column(default=1)
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Add to `backend/alembic/env.py` next to the VaultItem import:

```python
from app.models.track import InterviewBrief, Track  # noqa: F401  (registers tables)
```

Migrate BOTH databases:

```bash
cd backend && uv run alembic revision --autogenerate -m "create tracks and interview_briefs" && uv run alembic upgrade head
DATABASE_URL="postgresql+asyncpg://interview:interview@localhost:5432/interviewcopilot_test" uv run alembic upgrade head
```

Extend `clean_users_table` in `backend/tests/conftest.py` (delete tracks before users):

```python
from app.models.track import InterviewBrief, Track
# inside the fixture, before deleting users:
        await session.execute(delete(InterviewBrief))
        await session.execute(delete(Track))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_track_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): tracks and versioned interview_briefs models"
```

---

### Task 2: Track Creator Agent + services + routes

**Files:**
- Create: `backend/app/agents/track_creator.py`
- Create: `backend/app/services/track_service.py`
- Create: `backend/app/api/v1/tracks.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_tracks.py`

**Interfaces:**
- Consumes: `structured_completion`, `vault_service.vault_summary`, `get_current_user`, `get_db`.
- Produces:
  - `app.agents.track_creator.InterviewBriefContent` (pydantic): `summary: str`, `preparation_plan: list[str]`, `competencies: list[Competency]` where `Competency = {name, description, importance: Literal["core","important","nice_to_have"]}`, `question_areas: list[QuestionArea]` where `QuestionArea = {topic, guidance}`, `candidate_angle_notes: str`.
  - `app.agents.track_creator.build_track_creator_graph(turn_runner=...)` — node `author` → structured call.
  - `app.services.track_service.create_track_with_brief(db, user, track_type, subject, company, jd_text, request_id=None) -> dict` (keys `track`, `brief`); `list_tracks(db, user) -> list[dict]` (each with `brief_version`); `get_track_with_brief(db, user, track_id) -> dict | None`.
  - Routes: `POST /api/v1/tracks`, `GET /api/v1/tracks`, `GET /api/v1/tracks/{track_id}`, `GET /api/v1/tracks/{track_id}/brief` (latest). 404 for other users' tracks. 422 when `company_jd` without `jd_text`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_tracks.py`:

```python
import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User


async def _create_user() -> tuple[User, str]:
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"tr-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, create_access_token(str(user.id))


def _fake_brief_payload():
    return {
        "summary": "DSA interview with focus on arrays and hashing",
        "preparation_plan": ["Revise hashing", "Practice two-pointer problems"],
        "competencies": [
            {"name": "Arrays", "description": "Array manipulation", "importance": "core"}
        ],
        "question_areas": [{"topic": "Hashmaps", "guidance": "trade-offs of hash collisions"}],
        "candidate_angle_notes": "Probe the recommendation-system project for DS choices.",
    }


@pytest.mark.asyncio
async def test_create_track_generates_brief_v1(monkeypatch, clean_users_table):
    from app.agents.track_creator import InterviewBriefContent

    user, token = await _create_user()
    content = InterviewBriefContent.model_validate(_fake_brief_payload())

    async def fake_turn(*args, **kwargs):
        return content

    import app.services.track_service as svc

    monkeypatch.setattr(svc, "run_track_creator_turn", fake_turn)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tracks",
            json={"track_type": "topic", "subject": "Data Structures & Algorithms"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["track"]["subject"] == "Data Structures & Algorithms"
    assert body["brief"]["version"] == 1
    assert body["brief"]["content"]["summary"].startswith("DSA interview")


@pytest.mark.asyncio
async def test_company_jd_requires_jd_text(clean_users_table):
    user, token = await _create_user()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tracks",
            json={"track_type": "company_jd", "subject": "SDE Intern", "company": "Acme"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tracks_require_auth():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/tracks")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_tracks.py -v`
Expected: FAIL — import error / 404.

- [ ] **Step 3: Implement**

Create `backend/app/agents/track_creator.py`:

```python
import httpx
from typing import Literal, TypedDict

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
```

Create `backend/app/services/track_service.py`:

```python
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.track_creator import build_track_creator_graph
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.services.vault_service import vault_summary


async def run_track_creator_turn(**kwargs):
    from app.agents.track_creator import run_track_creator_turn as _run

    return await _run(**kwargs)


async def create_track_with_brief(
    db: AsyncSession,
    user: User,
    *,
    track_type: str,
    subject: str,
    company: str | None = None,
    jd_text: str | None = None,
    request_id: str | None = None,
) -> dict:
    track = Track(
        user_id=user.id,
        track_type=track_type,
        subject=subject,
        company=company,
        jd_text=jd_text,
    )
    db.add(track)
    await db.commit()
    await db.refresh(track)

    graph = build_track_creator_graph(turn_runner=run_track_creator_turn)
    result = await graph.ainvoke(
        {
            "objective": {
                "track_type": track_type,
                "subject": subject,
                "company": company,
                "jd_text": jd_text,
            },
            "vault_summary": await vault_summary(db, user.id),
        }
    )
    content = result["brief"]

    brief = InterviewBrief(track_id=track.id, version=1, content=content)
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return {"track": _track_dict(track), "brief": _brief_dict(brief)}


async def list_tracks(db: AsyncSession, user: User) -> list[dict]:
    result = await db.execute(
        select(Track).where(Track.user_id == user.id).order_by(Track.created_at.desc())
    )
    tracks = []
    for t in result.scalars().all():
        latest = await _latest_brief(db, t.id)
        d = _track_dict(t)
        d["brief_version"] = latest.version if latest else 0
        tracks.append(d)
    return tracks


async def get_track_with_brief(db: AsyncSession, user: User, track_id: uuid.UUID) -> dict | None:
    track = await db.get(Track, track_id)
    if track is None or track.user_id != user.id:
        return None
    latest = await _latest_brief(db, track.id)
    return {"track": _track_dict(track), "brief": _brief_dict(latest) if latest else None}


async def _latest_brief(db: AsyncSession, track_id) -> InterviewBrief | None:
    result = await db.execute(
        select(InterviewBrief)
        .where(InterviewBrief.track_id == track_id)
        .order_by(InterviewBrief.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _track_dict(t: Track) -> dict:
    return {
        "id": str(t.id),
        "track_type": t.track_type,
        "subject": t.subject,
        "company": t.company,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
    }


def _brief_dict(b: InterviewBrief) -> dict:
    return {"version": b.version, "content": b.content, "created_at": b.created_at.isoformat()}
```

Create `backend/app/api/v1/tracks.py`:

```python
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import track_service

router = APIRouter(prefix="/tracks", tags=["tracks"])


class CreateTrack(BaseModel):
    track_type: Literal["topic", "role", "company_jd"]
    subject: str = Field(max_length=255)
    company: str | None = Field(default=None, max_length=255)
    jd_text: str | None = None


@router.post("", status_code=201)
async def create_track(
    body: CreateTrack,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.track_type == "company_jd" and not body.jd_text:
        raise HTTPException(status_code=422, detail="company_jd tracks require jd_text")
    return await track_service.create_track_with_brief(
        db,
        user,
        track_type=body.track_type,
        subject=body.subject,
        company=body.company,
        jd_text=body.jd_text,
    )


@router.get("")
async def list_tracks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await track_service.list_tracks(db, user)


@router.get("/{track_id}")
async def get_track(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await track_service.get_track_with_brief(db, user, track_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return result


@router.get("/{track_id}/brief")
async def get_brief(
    track_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await track_service.get_track_with_brief(db, user, track_id)
    if result is None or result["brief"] is None:
        raise HTTPException(status_code=404, detail="Brief not found")
    return result["brief"]
```

Modify `backend/app/main.py` — import and register the tracks router (same pattern as onboarding/vault).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_tracks.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): track creator agent (langgraph), tracks api, versioned briefs"
```

---

### Task 3: README, live acceptance, push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append M4 section:**

```markdown
### Tracks & Interview Brief (M4)

- Create a topic track: `curl -s -X POST http://localhost:8000/api/v1/tracks -H "Content-Type: application/json" --cookie "ic_access=<token>" -d '{"track_type":"topic","subject":"Data Structures & Algorithms"}'` — the Track Creator Agent authors Brief v1.
- List tracks / open one: `GET /api/v1/tracks`, `GET /api/v1/tracks/{id}`, `GET /api/v1/tracks/{id}/brief`.
```

- [ ] **Step 2: Full suite + lint, live acceptance** (real LLM: create a topic track, verify brief content, list tracks), then:

```bash
git add -A
git commit -m "docs: tracks quickstart in README"
git push -u origin feat/m4-tracks-brief
```

---

## M4 Acceptance (from spec §14)

- [ ] Topic/role track created via API; Interview Brief v1 generated (real LLM) and versioned
- [ ] `GET /tracks/{id}/brief` returns the brief; 404/422 edges work; suite green; pushed
