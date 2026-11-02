# InterviewCopilot M3 — Onboarding & Candidate Context Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Onboarding Agent — the first of the four LangGraph agents — holds a conversation that turns a student's story into structured vault entries, and a resume upload lands its content in the vault too, all visible via API.

**Architecture:** Vault rows live in Postgres (`vault_items`, JSONB details, FK cascade to users); raw onboarding conversation lives in Mongo. The agent is a LangGraph `StateGraph` whose single decision node calls the LLM through a new `structured_completion` gateway helper (JSON mode + schema validation + one repair retry). Persistence stays in the service layer — the graph owns the LLM decision, the service owns I/O. Resumes go to SeaweedFS (boto3, path-style) then pypdf text extraction then a structured LLM call.

**Tech Stack:** langgraph, pypdf, python-multipart, boto3 (new); existing FastAPI/SQLAlchemy/Motor stack.

**Spec:** `docs/superpowers/specs/2026-11-02-interviewcopilot-v1-build-design.md` (M3 row of §14)

## Global Constraints

- Same as M1/M2 (Python 3.13 + uv, Git Bash, conventional commits, secrets in root `.env`, integration tests need the docker stack up).
- All LLM traffic only via `app.gateway.llm.chat_completion`; no direct provider calls.
- Compose commands use `--env-file ../.env` from `infra/`.
- All new routes require auth (`get_current_user`).

---

### Task 1: S3 settings + boto3 client for SeaweedFS

**Files:**
- Modify: `backend/app/core/config.py` (S3 fields)
- Create: `backend/app/db/s3.py`
- Modify: `backend/pyproject.toml` (boto3)
- Test: `backend/tests/test_s3.py`

**Interfaces:**
- Consumes: env vars `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` (already in `.env`).
- Produces: `Settings.s3_endpoint_url`, `Settings.s3_access_key`, `Settings.s3_secret_key`; `app.db.s3.get_s3_client()` (boto3 client, path-style addressing); `app.db.s3.ensure_bucket(s3, bucket: str)` (idempotent); constant `app.db.s3.RESUME_BUCKET = "resumes"`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_s3.py`:

```python
from app.db.s3 import RESUME_BUCKET, ensure_bucket, get_s3_client


def test_ensure_bucket_idempotent():
    s3 = get_s3_client()
    ensure_bucket(s3, RESUME_BUCKET)
    ensure_bucket(s3, RESUME_BUCKET)  # second call must not raise
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert RESUME_BUCKET in buckets
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_s3.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_s3_client'`.

- [ ] **Step 3: Implement**

Add to `backend/pyproject.toml` dependencies: `"boto3>=1.35",` (via `uv add boto3`).

Append to `Settings` in `backend/app/core/config.py` (after the LLM gateway block):

```python
    # S3-compatible object storage (SeaweedFS)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "local"
    s3_secret_key: str = "local"
```

Create `backend/app/db/s3.py`:

```python
import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

RESUME_BUCKET = "resumes"


def get_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket(s3: BaseClient, bucket: str) -> None:
    """Create the bucket if missing; safe to call on every request."""
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_s3.py -v`
Expected: PASS (1 passed) — requires SeaweedFS container up.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): boto3 s3 client for seaweedfs with idempotent bucket setup"
```

---

### Task 2: VaultItem model + conversation store

**Files:**
- Create: `backend/app/models/vault.py`
- Modify: `backend/alembic/env.py` (import Vault's Base metadata — already shared via `app.models.user.Base`; add import of vault module so table registers)
- Create: migration via autogenerate
- Create: `backend/app/services/__init__.py` (empty), `backend/app/services/conversation_store.py`
- Modify: `backend/tests/conftest.py` (extend cleanup to vault_items)
- Test: `backend/tests/test_vault.py`

**Interfaces:**
- Consumes: `Base` from `app.models.user`, `get_db`, Mongo via `get_mongo_db()`.
- Produces: `app.models.vault.VaultItem` — `id: uuid`, `user_id: uuid (FK users.id, ondelete CASCADE)`, `category: str`, `title: str`, `details: dict` (JSONB), `source: str` (`onboarding_chat` | `resume` | `manual`), `created_at`, `updated_at`; `app.services.conversation_store.append_message(mongo_db, user_id: str, role: str, content: str)` and `get_messages(mongo_db, user_id: str, limit: int = 50) -> list[dict]` (each `{role, content, created_at}` oldest-first).
- Note: `VaultItem.category` values enforced at the schema layer (`project|internship|skill|achievement|education|other`), not by a DB enum — keeps migrations cheap.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_vault.py`:

```python
import uuid

import pytest

from app.db.mongo import get_mongo_client
from app.db.sqlalchemy import SessionFactory
from app.models.user import User
from app.models.vault import VaultItem
from app.services.conversation_store import append_message, get_messages


@pytest.mark.asyncio
async def test_vault_item_roundtrip(clean_users_table):
    async with SessionFactory() as session:
        user = User(
            google_sub=f"sub-{uuid.uuid4()}",
            email=f"v-{uuid.uuid4()}@example.com",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        item = VaultItem(
            user_id=user.id,
            category="project",
            title="Recommender system",
            details={"role": "solo", "stack": "python"},
            source="onboarding_chat",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        assert item.id is not None
        assert item.details["role"] == "solo"


@pytest.mark.asyncio
async def test_conversation_append_and_read():
    mongo_db = get_mongo_client()["interviewcopilot_test"]
    user_id = str(uuid.uuid4())
    await mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
    await append_message(mongo_db, user_id, "user", "I built a robot")
    await append_message(mongo_db, user_id, "assistant", "Tell me more")
    msgs = await get_messages(mongo_db, user_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    await mongo_db.onboarding_conversations.delete_many({"user_id": user_id})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_vault.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.vault'`.

- [ ] **Step 3: Implement**

Create `backend/app/models/vault.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class VaultItem(Base):
    __tablename__ = "vault_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Add `from app.models.vault import VaultItem  # noqa: F401  (registers table)` to `backend/alembic/env.py` next to the existing `Base` import.

Migration:

```bash
cd backend && uv run alembic revision --autogenerate -m "create vault_items table" && uv run alembic upgrade head
```

Create `backend/app/services/__init__.py` (empty) and `backend/app/services/conversation_store.py`:

```python
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

CONVERSATIONS = "onboarding_conversations"


async def append_message(
    mongo_db: AsyncIOMotorDatabase, user_id: str, role: str, content: str
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await mongo_db[CONVERSATIONS].update_one(
        {"user_id": user_id},
        {
            "$push": {"messages": {"role": role, "content": content, "created_at": now}},
            "$set": {"updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def get_messages(
    mongo_db: AsyncIOMotorDatabase, user_id: str, limit: int = 50
) -> list[dict]:
    doc = await mongo_db[CONVERSATIONS].find_one({"user_id": user_id})
    if not doc:
        return []
    return doc.get("messages", [])[-limit:]
```

Extend `backend/tests/conftest.py` cleanup (replace file):

```python
import pytest
from sqlalchemy import delete

from app.db.sqlalchemy import SessionFactory
from app.models.user import User
from app.models.vault import VaultItem


@pytest.fixture
async def clean_users_table():
    """Remove vault items and users after a DB-touching test so reruns stay idempotent."""
    yield
    async with SessionFactory() as session:
        await session.execute(delete(VaultItem))
        await session.execute(delete(User))
        await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_vault.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): vault_items model, migration, mongo conversation store"
```

---

### Task 3: structured_completion gateway helper

**Files:**
- Create: `backend/app/gateway/structured.py`
- Test: `backend/tests/test_structured.py`

**Interfaces:**
- Consumes: `app.gateway.llm.chat_completion`, `LLMGatewayError`.
- Produces: `app.gateway.structured.structured_completion(client, *, system: str, user_payload: dict, schema: type[BaseModel], model: str = "structured-json", mongo_db=None, request_id=None) -> BaseModel`. Validates JSON against the pydantic schema; on parse/validation failure appends the bad output plus a correction instruction and retries once; raises `LLMGatewayError` after the second failure. This is THE function every agent uses for structured output.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_structured.py`:

```python
import httpx
import pytest
from pydantic import BaseModel

from app.gateway.structured import structured_completion


class Out(BaseModel):
    reply: str
    count: int


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_valid_json_parses_first_try():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"reply": "hi", "count": 2}'}}]})

    async with _client(handler) as client:
        out = await structured_completion(
            client, system="s", user_payload={"x": 1}, schema=Out
        )
    assert out.reply == "hi"
    assert out.count == 2


@pytest.mark.asyncio
async def test_repairs_after_invalid_json():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = (
            "not json at all"
            if calls["n"] == 1
            else '{"reply": "fixed", "count": 1}'
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    async with _client(handler) as client:
        out = await structured_completion(
            client, system="s", user_payload={}, schema=Out
        )
    assert calls["n"] == 2
    assert out.reply == "fixed"


@pytest.mark.asyncio
async def test_raises_after_second_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "still not json"}}]})

    async with _client(handler) as client:
        with pytest.raises(Exception):
            await structured_completion(
                client, system="s", user_payload={}, schema=Out
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_structured.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.gateway.structured'`.

- [ ] **Step 3: Implement**

Create `backend/app/gateway/structured.py`:

```python
import json

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ValidationError

from app.gateway.llm import LLMGatewayError, chat_completion


async def structured_completion(
    client: httpx.AsyncClient,
    *,
    system: str,
    user_payload: dict,
    schema: type[BaseModel],
    model: str = "structured-json",
    mongo_db: AsyncIOMotorDatabase | None = None,
    request_id: str | None = None,
) -> BaseModel:
    """Ask for JSON, validate against schema, repair once, then give up.

    Agents use this for every structured decision (extraction, question
    planning, evidence scoring). Raises LLMGatewayError if the model cannot
    produce schema-valid JSON within two attempts.
    """
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]
    last_error: Exception | None = None
    for _ in range(2):
        raw = await chat_completion(
            client,
            model=model,
            messages=messages,
            mongo_db=mongo_db,
            request_id=request_id,
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(raw)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous output was invalid: {exc}. "
                        "Respond with ONLY corrected JSON matching the required schema."
                    ),
                }
            )
    raise LLMGatewayError(f"structured output invalid after repair retry: {last_error}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_structured.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): structured_completion with schema validation and repair retry"
```

---

### Task 4: Onboarding Agent (LangGraph) + services + routes

**Files:**
- Create: `backend/app/agents/__init__.py` (empty), `backend/app/agents/onboarding.py`
- Create: `backend/app/services/vault_service.py`, `backend/app/services/onboarding_service.py`
- Create: `backend/app/api/v1/onboarding.py`, `backend/app/api/v1/vault.py`
- Modify: `backend/app/main.py` (register routers)
- Modify: `backend/pyproject.toml` (`uv add langgraph pypdf python-multipart`)
- Test: `backend/tests/test_onboarding.py`

**Interfaces:**
- Consumes: `structured_completion`, `VaultItem`, `conversation_store`, `get_current_user`, `get_db`, Mongo lifespan state.
- Produces:
  - `app.agents.onboarding.OnboardingTurn` (pydantic: `reply: str`, `extracted_items: list[ExtractedItem]`, `onboarding_complete: bool = False`), `app.agents.onboarding.ExtractedItem` (`category: Literal["project","internship","skill","achievement","education","other"]`, `title: str`, `details: dict[str,str] = {}`), `app.agents.onboarding.build_onboarding_graph() -> langgraph CompiledGraph` (node `intake` calls structured_completion).
  - `app.services.vault_service.create_items(db, user_id, items: list[ExtractedItem], source: str) -> list[VaultItem]`, `list_items(db, user_id) -> list[VaultItem]`, `vault_summary(db, user_id) -> list[dict]` (`[{category, title}]`).
  - `app.services.onboarding_service.chat(db, mongo_db, client, user, message: str, request_id=None) -> dict` with keys `reply`, `items_created`, `onboarding_complete`.
  - Routes: `POST /api/v1/onboarding/chat` `{message}`; `GET /api/v1/onboarding/state` → `{messages, vault_items}`; `GET /api/v1/vault/items`; `POST /api/v1/vault/items` `{category,title,details}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_onboarding.py`:

```python
import uuid

import httpx
import pytest

from app.agents.onboarding import ExtractedItem, OnboardingTurn
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User


@pytest.mark.asyncio
async def test_chat_creates_vault_items_and_replies(monkeypatch, clean_users_table):
    from app.db.mongo import get_mongo_client

    email = f"o-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))

    turn = OnboardingTurn(
        reply="Great, tell me about your stack!",
        extracted_items=[
            ExtractedItem(
                category="project", title="Line follower robot", details={"role": "solo"}
            )
        ],
    )

    async def fake_turn(*args, **kwargs):
        return turn

    import app.services.onboarding_service as svc

    monkeypatch.setattr(svc, "run_onboarding_turn", fake_turn)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/onboarding/chat",
            json={"message": "I built a line follower robot solo"},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "stack" in body["reply"]
    assert body["items_created"][0]["title"] == "Line follower robot"

    async with SessionFactory() as session:
        from sqlalchemy import select

        from app.models.vault import VaultItem

        items = (
            (await session.execute(select(VaultItem).where(VaultItem.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(items) == 1 and items[0].source == "onboarding_chat"

    mongo_db = get_mongo_client()["interviewcopilot"]
    await mongo_db.onboarding_conversations.delete_many({"user_id": str(user.id)})


@pytest.mark.asyncio
async def test_onboarding_requires_auth():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/onboarding/chat", json={"message": "hi"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_onboarding.py -v`
Expected: FAIL — import error (`app.agents` missing) / 404.

- [ ] **Step 3: Implement**

`uv add langgraph pypdf python-multipart`

Create `backend/app/agents/onboarding.py`:

```python
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.gateway.structured import structured_completion

ITEM_CATEGORIES = Literal["project", "internship", "skill", "achievement", "education", "other"]

SYSTEM_PROMPT = """You are the InterviewCopilot onboarding interviewer. Your job is to
truly understand the student behind the resume.

Rules:
- Ask about ONE thing at a time: their projects (problem, their personal role, methods,
  alternatives considered, what failed, how they evaluated results, limitations, what
  they would improve now), internships, skills, achievements, and education.
- Dig below surface claims. "Built an AI system" is a start; ask what problem it solved,
  what THEY implemented, and what did not work.
- Whenever the student shares concrete information, record it in extracted_items using
  the category taxonomy. details must hold short factual key points.
- reply must be warm, concise (max 3 sentences), and ask exactly one follow-up question.
- Set onboarding_complete=true only when you have projects AND skills AND education.
"""


class ExtractedItem(BaseModel):
    category: ITEM_CATEGORIES
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


class OnboardingTurn(BaseModel):
    reply: str
    extracted_items: list[ExtractedItem] = []
    onboarding_complete: bool = False


class OnboardingState(TypedDict, total=False):
    message: str
    history: list[dict]
    vault_summary: list[dict]
    turn: dict


async def run_onboarding_turn(
    *, message: str, history: list[dict], vault_summary: list[dict]
) -> OnboardingTurn:
    payload = {
        "known_vault_summary": vault_summary,
        "conversation_so_far": history,
        "new_user_message": message,
    }
    return await structured_completion(
        None,  # client injected via closure-free call path
        system=SYSTEM_PROMPT,
        user_payload=payload,
        schema=OnboardingTurn,
    )
```

Wait — `structured_completion` requires an `httpx.AsyncClient`. Pass one in: `run_onboarding_turn` creates its own client internally:

```python
async def run_onboarding_turn(
    *, message: str, history: list[dict], vault_summary: list[dict]
) -> OnboardingTurn:
    import httpx

    from app.core.config import get_settings

    payload = {
        "known_vault_summary": vault_summary,
        "conversation_so_far": history,
        "new_user_message": message,
    }
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        return await structured_completion(
            client,
            system=SYSTEM_PROMPT,
            user_payload=payload,
            schema=OnboardingTurn,
        )


def build_onboarding_graph():
    async def intake(state: OnboardingState) -> dict:
        turn = await run_onboarding_turn(
            message=state["message"],
            history=state.get("history", []),
            vault_summary=state.get("vault_summary", []),
        )
        return {"turn": turn.model_dump()}

    graph = StateGraph(OnboardingState)
    graph.add_node("intake", intake)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", END)
    return graph.compile()
```

Add `llm_client_timeout: int = 90` to `Settings` in config.py.

Create `backend/app/services/vault_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.models.vault import VaultItem


async def create_items(
    db: AsyncSession, user_id, items: list[ExtractedItem], source: str
) -> list[VaultItem]:
    rows = [
        VaultItem(
            user_id=user_id,
            category=i.category,
            title=i.title,
            details=i.details,
            source=source,
        )
        for i in items
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def list_items(db: AsyncSession, user_id) -> list[VaultItem]:
    result = await db.execute(
        select(VaultItem).where(VaultItem.user_id == user_id).order_by(VaultItem.created_at)
    )
    return list(result.scalars().all())


async def vault_summary(db: AsyncSession, user_id) -> list[dict]:
    return [{"category": i.category, "title": i.title} for i in await list_items(db, user_id)]
```

Create `backend/app/services/onboarding_service.py`:

```python
import httpx

from app.agents.onboarding import ExtractedItem, build_onboarding_graph
from app.db.mongo import AsyncIOMotorDatabaseStub  # placeholder — see below
from app.services import conversation_store
from app.services.vault_service import create_items, vault_summary
```

Final version (replace the placeholder import — Motor types come from motor directly):

```python
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem, build_onboarding_graph
from app.models.user import User
from app.services import conversation_store
from app.services.vault_service import create_items, vault_summary

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_onboarding_graph()
    return _graph


async def chat(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    user: User,
    message: str,
    request_id: str | None = None,
) -> dict:
    await conversation_store.append_message(mongo_db, str(user.id), "user", message)
    history = await conversation_store.get_messages(mongo_db, str(user.id), limit=20)
    summary = await vault_summary(db, user.id)

    result = await _get_graph().ainvoke(
        {"message": message, "history": history, "vault_summary": summary}
    )
    turn = result["turn"]

    created = await create_items(
        db, user.id, [ExtractedItem(**i) for i in turn["extracted_items"]], "onboarding_chat"
    )
    await conversation_store.append_message(mongo_db, str(user.id), "assistant", turn["reply"])
    return {
        "reply": turn["reply"],
        "items_created": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in created
        ],
        "onboarding_complete": turn["onboarding_complete"],
    }
```

Create `backend/app/api/v1/onboarding.py`:

```python
import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services import conversation_store, onboarding_service
from app.services.vault_service import list_items, vault_summary

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(body: ChatRequest, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        pass  # client unused directly; agent creates its own — kept for symmetry
    result = await onboarding_service.chat(
        db,
        request.app.state.mongo_db,
        user,
        body.message,
        request_id=request.headers.get("x-request-id"),
    )
    return result


@router.get("/state")
async def state(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    mongo_db = request.app.state.mongo_db
    messages = await conversation_store.get_messages(mongo_db, str(user.id), limit=100)
    items = await list_items(db, user.id)
    return {
        "messages": messages,
        "vault_items": [
            {"id": str(i.id), "category": i.category, "title": i.title, "source": i.source}
            for i in items
        ],
        "summary": await vault_summary(db, user.id),
    }
```

Note: drop the pointless empty client block — final `chat` route:

```python
@router.post("/chat")
async def chat(body: ChatRequest, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await onboarding_service.chat(
        db,
        request.app.state.mongo_db,
        user,
        body.message,
        request_id=request.headers.get("x-request-id"),
    )
```

Create `backend/app/api/v1/vault.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.api.deps import get_current_user
from app.db.sqlalchemy import get_db
from app.models.user import User
from app.services.vault_service import create_items, list_items

router = APIRouter(prefix="/vault", tags=["vault"])


class ManualItem(BaseModel):
    category: str
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


@router.get("/items")
async def get_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await list_items(db, user.id)
    return [
        {
            "id": str(i.id),
            "category": i.category,
            "title": i.title,
            "details": i.details,
            "source": i.source,
        }
        for i in items
    ]


@router.post("/items")
async def add_item(body: ManualItem, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    created = await create_items(
        db, user.id, [ExtractedItem(**body.model_dump())], "manual"
    )
    i = created[0]
    return {"id": str(i.id), "category": i.category, "title": i.title}
```

Modify `backend/app/main.py` `register_routes`:

```python
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.vault import router as vault_router
```

```python
    app.include_router(onboarding_router, prefix="/api/v1")
    app.include_router(vault_router, prefix="/api/v1")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_onboarding.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): onboarding agent (langgraph) with vault services and routes"
```

---

### Task 5: Resume upload + extraction

**Files:**
- Create: `backend/app/services/resume_service.py`
- Modify: `backend/app/api/v1/vault.py` (resume route)
- Test: `backend/tests/test_resume.py`

**Interfaces:**
- Consumes: `get_s3_client`, `ensure_bucket`, `RESUME_BUCKET`, `structured_completion`, `vault_service.create_items`, `get_current_user`.
- Produces: `app.services.resume_service.process_resume(db, s3, user, filename: str, data: bytes, request_id=None) -> dict` (keys `items_created`, `s3_key`); route `POST /api/v1/vault/resume` (multipart `file`, PDF only, ≤10 MB).
- MINIMAL_PDF in the test is a tiny valid one-page PDF with extractable text.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_resume.py`:

```python
import uuid

import httpx
import pytest

from app.agents.onboarding import ExtractedItem
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User

# A minimal valid one-page PDF containing the text "Hello Resume".
MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
    b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 60>>stream\nBT /F1 24 Tf 100 700 Td (Hello Resume) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)


@pytest.mark.asyncio
async def test_resume_upload_creates_vault_items(monkeypatch, clean_users_table):
    from app.agents.onboarding import OnboardingTurn  # noqa: F401
    from sqlalchemy import select

    from app.models.vault import VaultItem
    from app.services.resume_service import ResumeExtraction

    email = f"r-{uuid.uuid4()}@example.com"
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(str(user.id))

    extraction = ResumeExtraction(
        items=[ExtractedItem(category="skill", title="C++", details={"level": "advanced"})]
    )

    async def fake_completion(client, **kwargs):
        return extraction

    import app.gateway.structured as structured_mod

    monkeypatch.setattr(structured_mod, "structured_completion", fake_completion)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items_created"][0]["title"] == "C++"
    assert body["s3_key"].startswith(f"{user.id}/")

    async with SessionFactory() as session:
        items = (
            (await session.execute(select(VaultItem).where(VaultItem.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(items) == 1 and items[0].source == "resume"


@pytest.mark.asyncio
async def test_resume_rejects_non_pdf():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("x.txt", b"plain text", "text/plain")},
            cookies={"ic_access": create_access_token(str(uuid.uuid4()))},
        )
    assert resp.status_code in (400, 415)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_resume.py -v`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Implement**

Create `backend/app/services/resume_service.py`:

```python
import uuid
from io import BytesIO

import httpx
from botocore.client import BaseClient
from pypdf import PdfReader
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.core.config import get_settings
from app.db.s3 import RESUME_BUCKET
from app.gateway.structured import structured_completion
from app.models.user import User
from app.services.vault_service import create_items

MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_RESUME_CHARS = 20000

RESUME_SYSTEM_PROMPT = """Extract the candidate's verifiable experience from this resume
text into structured vault items. Use only information present in the text. For each
project include their role, stack, and outcomes in details. Never invent items."""


class ResumeExtraction(BaseModel):
    items: list[ExtractedItem] = []


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


async def process_resume(
    db: AsyncSession,
    s3: BaseClient,
    user: User,
    filename: str,
    data: bytes,
    request_id: str | None = None,
) -> dict:
    key = f"{user.id}/{uuid.uuid4()}-{filename}"
    s3.put_object(Bucket=RESUME_BUCKET, Key=key, Body=data, ContentType="application/pdf")

    text = extract_pdf_text(data)[:MAX_RESUME_CHARS]
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        extraction = await structured_completion(
            client,
            system=RESUME_SYSTEM_PROMPT,
            user_payload={"resume_text": text},
            schema=ResumeExtraction,
            request_id=request_id,
        )
    created = await create_items(db, user.id, extraction.items, "resume")
    return {
        "items_created": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in created
        ],
        "s3_key": key,
    }
```

Modify `backend/app/api/v1/vault.py` — add:

```python
from fastapi import UploadFile

from app.db.s3 import ensure_bucket, get_s3_client
from app.services.resume_service import MAX_RESUME_BYTES, process_resume


@router.post("/resume")
async def upload_resume(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type != "application/pdf":
        from fastapi import HTTPException

        raise HTTPException(status_code=415, detail="Only PDF resumes are supported")
    data = await file.read()
    if len(data) > MAX_RESUME_BYTES:
        from fastapi import HTTPException

        raise HTTPException(status_code=413, detail="Resume exceeds 10 MB")
    s3 = get_s3_client()
    ensure_bucket(s3, "resumes")
    return await process_resume(db, s3, user, file.filename or "resume.pdf", data)
```

(final code should import HTTPException at top of file instead of inline — implementer's choice, keep imports clean)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_resume.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): resume upload to seaweedfs with pdf extraction into vault"
```

---

### Task 6: README, full acceptance, push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append M3 section to README quickstart:**

```markdown
### Onboarding & vault (M3)

With the API running and your `ic_access` cookie from Google sign-in:

- Chat: `curl -s -X POST http://localhost:8000/api/v1/onboarding/chat -H "Content-Type: application/json" --cookie "ic_access=<token>" -d '{"message":"I built a line-following robot"}'`
- See the vault: `curl -s http://localhost:8000/api/v1/vault/items --cookie "ic_access=<token>"`
- Upload a resume: `curl -s -X POST http://localhost:8000/api/v1/vault/resume --cookie "ic_access=<token>" -F "file=@resume.pdf"`
```

- [ ] **Step 2: Full suite + lint**

Run: `cd backend && uv run pytest -q && uv run ruff check .`
Expected: all green.

- [ ] **Step 3: Live acceptance (needs running stack + API)**

1. Sign in (browser) → get `ic_access` cookie.
2. `POST /onboarding/chat` with a real project sentence → expect conversational reply + `items_created`.
3. `GET /vault/items` → entries visible.
4. Upload a real PDF resume → items extracted.
5. Mongo `onboarding_conversations` has the thread.

- [ ] **Step 4: Commit and push**

```bash
git add -A
git commit -m "docs: onboarding + vault quickstart in README"
git push -u origin feat/m3-onboarding-vault
```

---

## M3 Acceptance (from spec §14)

- [ ] Onboarding conversation produces vault items (schema-validated, sourced `onboarding_chat`)
- [ ] Resume upload → PDF text → vault entries (sourced `resume`), file stored in SeaweedFS
- [ ] Vault visible via `GET /vault/items`; full suite green; pushed + PR
