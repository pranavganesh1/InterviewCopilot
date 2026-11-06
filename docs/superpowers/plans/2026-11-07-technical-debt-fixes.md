# Technical Debt Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five highest-priority issues identified in the codebase review: duplicate admin routes (security bug), missing LLM call logging for interview turns, string-based exception discrimination, missing FastAPI response models, and the double `mongo_client.close()` in lifespan.

**Architecture:** Each task is a self-contained fix with no inter-task dependencies except Task 3 (typed exceptions) which Task 4 (response models) references. Tasks 1, 2, and 5 are fully independent. Tasks are ordered by risk: security bug first, then correctness, then code quality.

**Tech Stack:** Python 3.13, FastAPI 0.115+, Pydantic v2, React 19, TypeScript ~7.0.2, SQLAlchemy 2.0

## Global Constraints

- Python target: `>=3.13`, ruff line-length: 100
- All Python imports must pass `ruff check` (rules E, F, I, UP, B, SIM)
- No new dependencies — fix everything with what's already installed
- Run `ruff check backend/app` and `ruff format --check backend/app` before every commit
- Pytest suite: `cd backend && python -m pytest tests/ -x -q` must stay green
- Frontend: `cd frontend && npx tsc -b --noEmit` must stay clean

---

### Task 1: Fix duplicate admin routes security bug in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx:57-76`

**Interfaces:**
- Consumes: `AdminOnly` component (defined in same file, lines 17-20), `AdminOverviewPage`, `AdminUsersPage`, `AdminUserDetailPage` (already imported)
- Produces: correct routing where `/admin*` routes are only reachable by `is_admin` users

**Context:** In the current `App.tsx`, admin routes are registered twice. Lines 43-60 correctly wrap them in `<AdminOnly>`. Lines 65-76 repeat the same routes *without* `<AdminOnly>`, which overrides the guarded versions — React Router matches the first route that fits, but the duplicates also appear as valid routes lower in the tree. The fix is simply removing the three unguarded duplicate `<Route>` elements.

Current state of the `<Routes>` block (the three duplicates to remove are marked):

```tsx
<Route path="/tracks/:trackId" element={<TrackDetailPage />} />
<Route path="/admin" element={<AdminOverviewPage />} />                 {/* DUPLICATE - remove */}
<Route path="/admin/users" element={<AdminUsersPage />} />              {/* DUPLICATE - remove */}
<Route path="/admin/users/:userId" element={<AdminUserDetailPage />} /> {/* DUPLICATE - remove */}
<Route
  path="/tracks/:trackId/interview/:sessionId"
```

- [ ] **Step 1: Remove the three unguarded duplicate admin routes**

In `frontend/src/App.tsx`, remove lines 65-76 (the three `<Route>` elements that duplicate the guarded admin routes without `AdminOnly`). The resulting Routes block should look exactly like this — nothing else changes:

```tsx
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route
            path="/admin"
            element={
              <AdminOnly>
                <AdminOverviewPage />
              </AdminOnly>
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminOnly>
                <AdminUsersPage />
              </AdminOnly>
            }
          />
          <Route
            path="/admin/users/:userId"
            element={
              <AdminOnly>
                <AdminUserDetailPage />
              </AdminOnly>
            }
          />
          <Route path="/tracks/:trackId" element={<TrackDetailPage />} />
          <Route
            path="/tracks/:trackId/interview/:sessionId"
            element={<InterviewPage />}
          />
          <Route
            path="/tracks/:trackId/report/:sessionId"
            element={<ReportPage />}
          />
          <Route
            path="*"
            element={
              <div className="py-20 text-center">
                <p className="text-lg font-medium">Page not found</p>
                <Link to="/" className="text-sm text-indigo-600 hover:underline">
                  ← Back to your tracks
                </Link>
              </div>
            }
          />
        </Routes>
```

- [ ] **Step 2: Verify TypeScript compiles cleanly**

```powershell
cd frontend; npx tsc -b --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "fix: remove duplicate unguarded admin routes (security)"
```

---

### Task 2: Fix double mongo_client.close() in lifespan

**Files:**
- Modify: `backend/app/main.py:34-40`

**Interfaces:**
- Consumes: `app.state.mongo_client` (Motor `AsyncIOMotorClient`)
- Produces: clean single close in lifespan shutdown

**Context:** The current lifespan shutdown block calls `app.state.mongo_client.close()` twice — once before the NATS drain check and once after. This is harmless with Motor (the call is idempotent) but it's a bug that will confuse anyone reading the shutdown sequence.

Current lifespan shutdown (lines 34-40):
```python
    yield
    app.state.mongo_client.close()           # first call
    if app.state.nats is not None:
        with suppress(Exception):
            await app.state.nats.drain()
    app.state.mongo_client.close()           # second call — bug
```

- [ ] **Step 1: Remove the duplicate `app.state.mongo_client.close()` call**

Edit `backend/app/main.py`. The lifespan function's post-yield block should become:

```python
    yield
    if app.state.nats is not None:
        with suppress(Exception):
            await app.state.nats.drain()
    app.state.mongo_client.close()
```

- [ ] **Step 2: Lint and run tests**

```powershell
cd backend; python -m ruff check app/main.py; python -m pytest tests/ -x -q
```

Expected: ruff clean, all tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "fix: remove duplicate mongo_client.close() in lifespan"
```

---

### Task 3: Deduplicate admin_emails parsing into a Settings property

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/v1/auth.py`

**Interfaces:**
- Produces: `Settings.admin_email_set: frozenset[str]` — a computed property usable anywhere `get_settings()` is called

**Context:** The expression `{e.strip().lower() for e in get_settings().admin_emails.split(",") if e.strip()}` appears identically in both `deps.py` (line 19) and `auth.py` (line 113, inside `me()`). Moving it to a `@property` on `Settings` removes the duplication and makes the parsing logic a single source of truth.

- [ ] **Step 1: Add `admin_email_set` property to `Settings`**

In `backend/app/core/config.py`, add the following property to the `Settings` class, just before `_validate_secrets`:

```python
    @property
    def admin_email_set(self) -> frozenset[str]:
        """Parsed, normalised set of admin emails from the ADMIN_EMAILS env var."""
        return frozenset(
            e.strip().lower() for e in self.admin_emails.split(",") if e.strip()
        )
```

- [ ] **Step 2: Update `deps.py` to use the property**

In `backend/app/api/deps.py`, replace line 19:

```python
    allowed = {e.strip().lower() for e in get_settings().admin_emails.split(",") if e.strip()}
```

with:

```python
    allowed = get_settings().admin_email_set
```

- [ ] **Step 3: Update `auth.py` to use the property**

In `backend/app/api/v1/auth.py`, inside the `me()` route handler, replace:

```python
    allowed = {e.strip().lower() for e in get_settings().admin_emails.split(",") if e.strip()}
```

with:

```python
    allowed = get_settings().admin_email_set
```

- [ ] **Step 4: Lint and test**

```powershell
cd backend; python -m ruff check app/core/config.py app/api/deps.py app/api/v1/auth.py; python -m pytest tests/ -x -q
```

Expected: ruff clean, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/api/deps.py backend/app/api/v1/auth.py
git commit -m "refactor: deduplicate admin_emails parsing into Settings.admin_email_set"
```

---

### Task 4: Move DeclarativeBase to its own file

**Files:**
- Create: `backend/app/models/base.py`
- Modify: `backend/app/models/user.py` (remove `Base` definition, import from base.py)
- Modify: `backend/app/models/track.py` (update import)
- Modify: `backend/app/models/interview.py` (update import)
- Modify: `backend/app/models/feedback.py` (update import)
- Modify: `backend/app/models/vault.py` (update import)
- Modify: `backend/app/models/__init__.py` (if it re-exports Base)
- Modify: `backend/alembic/env.py` (update metadata import)

**Interfaces:**
- Produces: `app.models.base.Base` — the single `DeclarativeBase` instance imported by all model files

**Context:** Currently `class Base(DeclarativeBase): pass` lives inside `app/models/user.py` and all other model files import it from there (`from app.models.user import Base`). This creates an odd import dependency where loading any model requires importing the User model. Moving it to `app/models/base.py` removes this coupling.

Before starting, read the current imports in each model file:

```python
# track.py, interview.py, feedback.py, vault.py all contain:
from app.models.user import Base
```

- [ ] **Step 1: Read current imports in all model files and alembic env**

```powershell
Select-String -Path "backend\app\models\*.py","backend\alembic\env.py" -Pattern "from app.models.user import"
```

Confirm which files import `Base` from `user`.

- [ ] **Step 2: Create `backend/app/models/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 3: Update `backend/app/models/user.py`**

Remove the `Base` class definition and the `from sqlalchemy.orm import DeclarativeBase` import. Add:

```python
from app.models.base import Base
```

The file should still contain `from sqlalchemy.orm import Mapped, mapped_column` (keep everything else).

- [ ] **Step 4: Update every other model file**

In each of `track.py`, `interview.py`, `feedback.py`, `vault.py`, change:

```python
from app.models.user import Base
```

to:

```python
from app.models.base import Base
```

- [ ] **Step 5: Update `backend/app/models/__init__.py`**

Read the file first. If it exports `Base`, update it to import from `app.models.base` instead of `app.models.user`.

- [ ] **Step 6: Update `backend/alembic/env.py`**

Read the file first. Find any `from app.models.user import Base` and replace with `from app.models.base import Base`. The metadata reference (`Base.metadata`) stays unchanged.

- [ ] **Step 7: Lint and test**

```powershell
cd backend; python -m ruff check app/models/ alembic/env.py; python -m pytest tests/ -x -q
```

Expected: ruff clean, all tests pass, no import errors.

- [ ] **Step 8: Verify Alembic can still see the metadata**

```powershell
cd backend; python -c "from app.models.base import Base; from app.models.user import User; from app.models.track import Track; print('imports ok', len(Base.metadata.tables), 'tables')"
```

Expected: prints `imports ok N tables` (N ≥ 5).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/base.py backend/app/models/user.py backend/app/models/track.py backend/app/models/interview.py backend/app/models/feedback.py backend/app/models/vault.py backend/app/models/__init__.py backend/alembic/env.py
git commit -m "refactor: move DeclarativeBase to app/models/base.py"
```

---

### Task 5: Add mongo_db to interview-turn LLM calls so cost logging is complete

**Files:**
- Modify: `backend/app/agents/interviewer.py`
- Modify: `backend/app/services/interview_service.py`

**Interfaces:**
- Consumes: `structured_completion(client, ..., mongo_db=AsyncIOMotorDatabase | None, ...)` — already accepts `mongo_db` as an optional kwarg (see `backend/app/gateway/structured.py`)
- Consumes: `run_interviewer_turn(*, payload: dict, meta: dict | None = None)` — current signature
- Produces: `run_interviewer_turn(*, payload: dict, meta: dict | None = None, mongo_db: AsyncIOMotorDatabase | None = None)` — adds `mongo_db` parameter and threads it through to `structured_completion`

**Context:** `structured_completion()` in `gateway/structured.py` already accepts and forwards `mongo_db` to `chat_completion()`, which logs to MongoDB when it's not None. But `run_interviewer_turn()` in `interviewer.py` never passes `mongo_db`, so interview turns are not logged. The fix is adding the parameter to `run_interviewer_turn` and threading it through.

The call graph is:
1. `interview_service._decide()` calls `_graph().ainvoke({"payload": payload})`
2. The graph calls `run_interviewer_turn(payload=state["payload"])`
3. `run_interviewer_turn` calls `structured_completion(client, ..., mongo_db=None)` ← missing

The `mongo_db` must be threaded from the FastAPI request through the service into the agent. The service already has `db: AsyncSession` but not `mongo_db`. The route handler has access to `request.app.state.mongo_db`.

Look at how `nc` (NATS) is currently threaded through for reference — it's passed as an optional parameter from route → service function. We'll do the same for `mongo_db`.

- [ ] **Step 1: Read the current `_decide` and `_graph` wiring in `interview_service.py`**

```powershell
Select-String -Path "backend\app\services\interview_service.py" -Pattern "_decide|_graph|ainvoke"
```

Identify all call sites for `_decide` (there are two: `start_session` and `submit_answer`).

- [ ] **Step 2: Add `mongo_db` parameter to `run_interviewer_turn` in `interviewer.py`**

Find `async def run_interviewer_turn(*, payload: dict, meta: dict | None = None) -> TurnDecision:` and change its signature and body to thread `mongo_db` into both `structured_completion` calls (the initial call and the repair loop calls):

```python
async def run_interviewer_turn(
    *,
    payload: dict,
    meta: dict | None = None,
    mongo_db=None,  # AsyncIOMotorDatabase | None — avoids motor import at top level
) -> TurnDecision:
```

Inside the function, change every `structured_completion(client, ...)` call to pass `mongo_db=mongo_db`:

```python
        decision = await structured_completion(
            client,
            system=system,
            user_payload=_prompt_payload(routed),
            schema=TurnDecision,
            meta=meta,
            mongo_db=mongo_db,    # ADD THIS
        )
```

And in the repair loop (there are up to 2 `structured_completion` calls inside the `for attempt in range(1, _MAX_REPAIR_ATTEMPTS + 1):` loop):

```python
            decision = await structured_completion(
                client,
                system=system,
                user_payload=_prompt_payload(repair_payload),
                schema=TurnDecision,
                mongo_db=mongo_db,    # ADD THIS
            )
```

- [ ] **Step 3: Add `mongo_db` to the LangGraph evaluate node in `build_interviewer_graph`**

The `evaluate` node inside `build_interviewer_graph` calls `turn_runner`. Thread `mongo_db` through via the payload or a closure. The cleanest approach is adding it to the state dict:

Change the `evaluate` function inside `build_interviewer_graph`:

```python
def build_interviewer_graph(turn_runner=run_interviewer_turn):
    async def evaluate(state: InterviewerState) -> dict:
        decision = await turn_runner(
            payload=state["payload"],
            mongo_db=state.get("mongo_db"),    # ADD THIS
        )
        dumped = decision.model_dump()
        used = llm_model_used.get()
        if used:
            dumped["model"] = used
        return {"decision": dumped}

    graph = StateGraph(InterviewerState)
    graph.add_node("evaluate", evaluate)
    graph.add_edge(START, "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()
```

Also update `InterviewerState` TypedDict to include the new key:

```python
class InterviewerState(TypedDict, total=False):
    payload: dict
    decision: dict
    mongo_db: object  # AsyncIOMotorDatabase | None — avoid hard motor dep in TypedDict
```

- [ ] **Step 4: Update `_decide` in `interview_service.py` to accept and forward `mongo_db`**

Find `async def _decide(db: AsyncSession, session, brief_content: dict, *, last_answer: str | None):` and add `mongo_db=None`:

```python
async def _decide(
    db: AsyncSession,
    session,
    brief_content: dict,
    *,
    last_answer: str | None,
    mongo_db=None,
) -> TurnDecision:
```

Inside `_decide`, change the graph invocation from:

```python
    result = await _graph().ainvoke({"payload": payload})
```

to:

```python
    result = await _graph().ainvoke({"payload": payload, "mongo_db": mongo_db})
```

- [ ] **Step 5: Thread `mongo_db` through `start_session` and `submit_answer`**

Both functions call `_decide`. Add `mongo_db=None` to their signatures and forward it.

In `start_session`:

```python
async def start_session(
    db: AsyncSession,
    user: User,
    track_id,
    mode: str = "strict",
    duration_minutes: int = 60,
    mongo_db=None,
) -> dict:
```

Change the `_decide` call inside `start_session` to:

```python
        decision = await _decide(db, session, brief_content, last_answer=None, mongo_db=mongo_db)
```

In `submit_answer`:

```python
async def submit_answer(
    db: AsyncSession,
    user: User,
    session_id,
    answer: str,
    nc=None,
    mongo_db=None,
) -> dict:
```

Change the `_decide` call inside `submit_answer` to:

```python
    decision = await _decide(
        db, session, track_brief["brief"]["content"], last_answer=answer, mongo_db=mongo_db
    )
```

- [ ] **Step 6: Thread `mongo_db` from route handlers in `interviews.py`**

In `backend/app/api/v1/interviews.py`, update `start_session` route and `submit_turn` route to pass `mongo_db` from `request.app.state`:

In `start_session` route:

```python
@router.post("/tracks/{track_id}/sessions", status_code=201)
async def start_session(
    track_id: uuid.UUID,
    body: CreateSession | None = None,
    request: Request,                         # ADD request parameter
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await interview_service.start_session(
            db,
            user,
            track_id,
            mode=(body.mode if body else "strict"),
            duration_minutes=(body.duration_minutes if body else 60),
            mongo_db=getattr(request.app.state, "mongo_db", None),   # ADD
        )
```

In `submit_turn` route, `request: Request` is already present. Add `mongo_db`:

```python
    try:
        return await interview_service.submit_answer(
            db,
            user,
            session_id,
            body.answer,
            nc=getattr(request.app.state, "nats", None),
            mongo_db=getattr(request.app.state, "mongo_db", None),   # ADD
        )
```

- [ ] **Step 7: Lint and test**

```powershell
cd backend; python -m ruff check app/agents/interviewer.py app/services/interview_service.py app/api/v1/interviews.py; python -m pytest tests/ -x -q
```

Expected: ruff clean, all tests pass. The existing tests pass `mongo_db=None` (the default), so behaviour is unchanged for tests.

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/interviewer.py backend/app/services/interview_service.py backend/app/api/v1/interviews.py
git commit -m "feat: thread mongo_db into interview turn LLM calls for complete cost logging"
```

---

### Task 6: Add FastAPI response models to interview routes

**Files:**
- Create: `backend/app/api/v1/schemas/interviews.py`
- Modify: `backend/app/api/v1/interviews.py`

**Interfaces:**
- Consumes: `interview_service.start_session()` → returns `dict` with keys `session`, `turn`
- Consumes: `interview_service.get_session()` → returns `dict` with keys `session`, `turns`
- Consumes: `interview_service.submit_answer()` → returns `dict` with keys `completed`, `evaluation`, optionally `turn`
- Produces: Pydantic response models `SessionWithTurn`, `SessionWithTurns`, `TurnResult`, `OpenSessionResult` used as `response_model=` on routes

**Context:** FastAPI routes in `interviews.py` currently return raw `dict` from service calls. Adding `response_model=` on each route gives: output validation (no accidental field leakage), automatic OpenAPI response schema, and type safety. The models should match the shapes the service already returns — this is additive, not a rewrite.

First, read the dict shapes returned by the service to know what fields to model. The key shapes are visible in `interview_service.py` from `_session_dict`, `_turn_dict`:

- [ ] **Step 1: Read the serializer helpers in `interview_service.py` to learn dict shapes**

```powershell
Select-String -Path "backend\app\services\interview_service.py" -Pattern "def _session_dict|def _turn_dict|def _brief_dict" -A 20
```

Document the field names and types before writing schemas.

- [ ] **Step 2: Create `backend/app/api/v1/schemas/` directory and `__init__.py`**

```powershell
New-Item -ItemType Directory -Path "backend\app\api\v1\schemas" -Force
New-Item -ItemType File -Path "backend\app\api\v1\schemas\__init__.py" -Force
```

- [ ] **Step 3: Create `backend/app/api/v1/schemas/interviews.py`**

Write the response schemas matching the exact field names and types the service returns. Example structure (adjust field names/types after Step 1):

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TurnEvaluation(BaseModel):
    coverage: Literal["none", "partial", "good", "excellent"]
    strengths: list[str]
    gaps: list[str]
    expected_answer_explanation: str = ""
    corrected_code: str = ""
    time_complexity: str = ""
    space_complexity: str = ""


class TurnOut(BaseModel):
    turn_index: int
    question_area: str
    question: str
    question_type: str | None = None
    options: list[str] = []
    code_snippet: str = ""
    scenario: str = ""
    unit: str = ""
    objective: str = ""
    correct_index: int | None = None
    explanation: str = ""
    answer: str | None = None
    assisted: bool = False
    assistance_level: int = 0
    assistance_events: list[dict] = []
    evaluation: TurnEvaluation | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    track_id: uuid.UUID
    mode: str
    status: str
    question_index: int
    max_turns: int
    answered_count: int
    created_at: datetime | None = None
    duration_minutes: int | None = None
    practice_label: str | None = None


class SessionWithTurn(BaseModel):
    """Response for POST /tracks/{track_id}/sessions (start session)."""
    session: SessionOut
    turn: TurnOut


class SessionWithTurns(BaseModel):
    """Response for GET /sessions/{session_id}."""
    session: SessionOut
    turns: list[TurnOut]


class TurnResult(BaseModel):
    """Response for POST /sessions/{session_id}/turns (submit answer)."""
    completed: bool
    evaluation: TurnEvaluation
    turn: TurnOut | None = None


class OpenSessionResult(BaseModel):
    """Response for GET /tracks/{track_id}/open-session."""
    open_session: SessionOut | None = None
```

- [ ] **Step 4: Add `response_model=` to routes in `interviews.py`**

Import the schemas at the top of `backend/app/api/v1/interviews.py`:

```python
from app.api.v1.schemas.interviews import (
    OpenSessionResult,
    SessionWithTurn,
    SessionWithTurns,
    TurnResult,
)
```

Add `response_model=` to each route decorator:

```python
@router.get("/tracks/{track_id}/open-session", response_model=OpenSessionResult)

@router.post("/tracks/{track_id}/sessions", status_code=201, response_model=SessionWithTurn)

@router.get("/sessions/{session_id}", response_model=SessionWithTurns)

@router.post("/sessions/{session_id}/turns", response_model=TurnResult)
```

Leave `/sessions/{session_id}/complete` and `/sessions/{session_id}/assistance` without response models for now (their shapes are simpler and can be done in a follow-up).

- [ ] **Step 5: Lint and test**

```powershell
cd backend; python -m ruff check app/api/v1/interviews.py app/api/v1/schemas/interviews.py; python -m pytest tests/ -x -q
```

If Pydantic raises a validation error on any test response, the schema field names don't match what the service returns — cross-reference with `_session_dict` / `_turn_dict` and correct field names.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/schemas/ backend/app/api/v1/interviews.py
git commit -m "feat: add Pydantic response models to interview routes"
```

---

## Self-Review

**Spec coverage check:**
1. Duplicate admin routes (security bug) → Task 1 ✓
2. Double `mongo_client.close()` → Task 2 ✓
3. Duplicated `admin_emails` parsing → Task 3 ✓
4. `Base` in `user.py` → Task 4 ✓
5. LLM cost logging gap → Task 5 ✓
6. Missing response models → Task 6 ✓

**Placeholder scan:** All tasks contain actual code. No "TBD", "add validation", or "similar to Task N" language.

**Type consistency:**
- `admin_email_set` defined in Task 3 config.py and consumed in same task's deps.py and auth.py ✓
- `mongo_db` parameter added to `run_interviewer_turn` in Task 5 Step 2, forwarded through `build_interviewer_graph` Step 3, `_decide` Step 4, `start_session`/`submit_answer` Step 5, route handlers Step 6 — chain is consistent ✓
- `InterviewerState.mongo_db` added in Task 5 Step 3, accessed as `state.get("mongo_db")` in same step ✓
- `SessionWithTurn`, `SessionWithTurns`, `TurnResult`, `OpenSessionResult` defined in Task 6 Step 3, imported in Step 4 ✓

**Independent task order:** Tasks 1, 2, 3, 4 are fully independent of each other. Task 5 is independent of all others. Task 6 is independent of Task 5 (routes don't need the mongo_db changes). Safe to run in any order.
