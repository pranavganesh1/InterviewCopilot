# InterviewCopilot M1 — Scaffold & Infra Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the repo skeleton: FastAPI backend with a green `/healthz`, full docker-compose infrastructure (Postgres, MongoDB, MinIO, NATS JetStream, LiteLLM proxy), structured logging with request IDs, and lint/format tooling — all committed.

**Architecture:** FastAPI modular monolith (async, Python 3.13, uv-managed). Infra per HLD v0.2 as five docker-compose services. Logging via structlog with per-request IDs. Milestone produces no business logic yet — only a verifiably healthy foundation.

**Tech Stack:** FastAPI, uvicorn, pydantic-settings, structlog, pytest + httpx, uv, Docker Compose, ruff, pre-commit.

**Spec:** `docs/superpowers/specs/2026-11-02-interviewcopilot-v1-build-design.md` (M1 row of §14)

## Global Constraints

- Budget: $0 — every service and API key free tier; no paid services.
- Python 3.13 (`requires-python = ">=3.13"`); dependency management via **uv**.
- Shell is Git Bash on Windows; quote paths containing spaces (`C:\MY STUFF\...`).
- Secrets never committed: real `.env` is git-ignored; only `.env.example` is committed.
- Conventional Commits (`feat:`, `chore:`, `test:`).
- Frontend is NOT in M1 scope (deferred to M2).
- Docker Desktop must be running before Task 3 (product owner starts it).

---

### Task 1: Backend scaffold with /healthz

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py` (empty)
- Create: `backend/app/core/__init__.py` (empty)
- Create: `backend/app/core/config.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/__init__.py` (empty), `backend/tests/test_healthz.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `app.main.create_app() -> FastAPI`, `app.main.app` (ASGI app); `app.core.config.get_settings() -> Settings` (cached) with fields `app_name: str = "InterviewCopilot"`, `app_env: str = "local"`, `log_level: str = "INFO"`. Later tasks and milestones import these exact names.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/__init__.py` (empty) and `backend/tests/test_healthz.py`:

```python
import httpx

from app.main import app


async def test_healthz_returns_ok():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Create the project files that make the test runnable, then verify the test fails**

Create `backend/pyproject.toml`:

```toml
[project]
name = "interviewcopilot-backend"
version = "0.1.0"
description = "InterviewCopilot FastAPI backend"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "pydantic-settings>=2.7",
    "structlog>=24.4",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "httpx>=0.28",
    "ruff>=0.9",
    "pre-commit>=4.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py313"
```

Create `backend/app/__init__.py`, `backend/app/core/__init__.py` as empty files, then `backend/app/core/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "InterviewCopilot"
    app_env: str = "local"  # local | staging | prod
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Run: `cd backend && uv sync && uv run pytest tests/test_healthz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'` (app.main.py does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/main.py`:

```python
from fastapi import FastAPI

from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, docs_url="/docs")
    register_routes(app)
    register_middleware(app)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}


def register_middleware(app: FastAPI) -> None:
    # Middleware is added in Task 2; kept as a seam so order stays explicit.
    pass


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_healthz.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): scaffold FastAPI app with healthz endpoint"
```

---

### Task 2: Structured logging + request-ID middleware

**Files:**
- Create: `backend/app/core/logging.py`
- Create: `backend/app/core/middleware.py`
- Modify: `backend/app/main.py` (wire middleware and logging config)
- Test: `backend/tests/test_request_id.py`

**Interfaces:**
- Consumes: `app.core.config.get_settings()` (fields `log_level`, `app_env`); `app.main.register_middleware`.
- Produces: `app.core.logging.configure_logging(log_level: str, json_logs: bool) -> None` and `app.core.logging.get_logger(name: str | None = None)`; `app.core.middleware.RequestIdMiddleware` — Starlette middleware that echoes/generates `X-Request-ID` response header and binds `request_id` into structlog contextvars. Later milestones use `get_logger(__name__)` for all logging.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_request_id.py`:

```python
import httpx

from app.main import app


async def test_healthz_returns_request_id_header():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) >= 32


async def test_healthz_echoes_incoming_request_id():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz", headers={"X-Request-ID": "test-trace-123"})
    assert resp.headers["X-Request-ID"] == "test-trace-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_request_id.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.middleware'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/core/logging.py`:

```python
import logging

import structlog


def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog once at app startup.

    json_logs=False gives a pretty console renderer for local dev.
    """
    logging.basicConfig(level=log_level, format="%(message)s")
    renderer = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
```

Create `backend/app/core/middleware.py`:

```python
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request/response carries an X-Request-ID and it is bound to logs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers["X-Request-ID"] = request_id
        return response
```

Modify `backend/app/main.py` — replace `register_middleware` and `create_app`:

```python
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        json_logs=settings.app_env != "local",  # pretty console logs locally
    )
    app = FastAPI(title=settings.app_name, docs_url="/docs")
    register_routes(app)
    register_middleware(app)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: PASS (3 passed: healthz + two request-ID tests).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): structlog config and X-Request-ID middleware"
```

---

### Task 3: Docker compose infrastructure

**Files:**
- Create: `infra/docker-compose.yml`
- Create: `infra/litellm/config.yaml`
- Create: `.env.example`

**Interfaces:**
- Consumes: nothing from backend (backend connects to these services in later milestones).
- Produces: local services reachable at `localhost:5432` (postgres), `localhost:27017` (mongo), `localhost:9000` (minio S3 API; console `:9001`), `localhost:4222` (nats; monitor `:8222`), `localhost:4000` (litellm proxy, OpenAI-compatible). `.env.example` defines every variable later milestones read: `DATABASE_URL`, `MONGO_URL`, `MINIO_ENDPOINT_URL`, `NATS_URL`, `LITELLM_URL`, `LITELLM_MASTER_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`. Later tasks must use these exact variable names.

**Prerequisite:** Docker Desktop is running (`docker ps` succeeds).

- [ ] **Step 1: Create `.env.example` at repo root**

```bash
# App
APP_ENV=local
LOG_LEVEL=INFO

# Postgres
POSTGRES_USER=interview
POSTGRES_PASSWORD=interview
POSTGRES_DB=interviewcopilot
DATABASE_URL=postgresql+asyncpg://interview:interview@localhost:5432/interviewcopilot

# MongoDB
MONGO_URL=mongodb://localhost:27017

# MinIO (S3-compatible object storage)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_ENDPOINT_URL=http://localhost:9000

# NATS
NATS_URL=nats://localhost:4222

# LLM gateway (LiteLLM proxy)
LITELLM_URL=http://localhost:4000
LITELLM_MASTER_KEY=sk-local-master
GROQ_API_KEY=
GEMINI_API_KEY=
```

Then copy it to the real `.env` (git-ignored): `cp .env.example .env`

- [ ] **Step 2: Create `infra/docker-compose.yml`**

```yaml
name: interviewcopilot

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-interview}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-interview}
      POSTGRES_DB: ${POSTGRES_DB:-interviewcopilot}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-interview}"]
      interval: 5s
      timeout: 3s
      retries: 10

  mongo:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    healthcheck:
      test: ["CMD-SHELL", "mongosh --quiet --eval \"db.adminCommand('ping').ok\" | grep -q 1"]
      interval: 5s
      timeout: 3s
      retries: 10

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 3s
      retries: 10

  nats:
    image: nats:2
    command: ["-js", "-m", "8222"]
    ports:
      - "4222:4222"
      - "8222:8222"
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O- http://localhost:8222/healthz || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10

  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    environment:
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY:-sk-local-master}
      GROQ_API_KEY: ${GROQ_API_KEY:-}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
    ports:
      - "4000:4000"
    volumes:
      - ./litellm/config.yaml:/app/config.yaml:ro
    healthcheck:
      test: ["CMD-SHELL", "timeout 10 bash -c ':> /dev/tcp/127.0.0.1/4000' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 12

volumes:
  postgres_data:
  mongo_data:
  minio_data:
```

- [ ] **Step 3: Create `infra/litellm/config.yaml`**

Same `model_name` listed twice = router deployment list: primary Groq, fallback Gemini on failure (LiteLLM retries the next deployment of the same group).

```yaml
model_list:
  - model_name: interview-chat
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
  - model_name: interview-chat
    litellm_params:
      model: gemini/gemini-2.0-flash
      api_key: os.environ/GEMINI_API_KEY
  - model_name: structured-json
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
      response_format: {"type": "json_object"}
  - model_name: structured-json
    litellm_params:
      model: gemini/gemini-2.0-flash
      api_key: os.environ/GEMINI_API_KEY

litellm_settings:
  num_retries: 2
  timeout: 60
```

- [ ] **Step 4: Validate and start the stack**

Run: `cd infra && docker compose config --quiet && docker compose up -d`
Expected: no config errors; five services created.

Run: `sleep 30 && docker compose ps`
Expected: all five services `Up (healthy)`. Note: litellm may take ~30–60 s on first pull/start; if `Restarting`, run `docker compose logs litellm` and check for a config parse error before anything else.

- [ ] **Step 5: Smoke-test reachable endpoints**

Run: `curl -s http://localhost:8222/healthz` → expected `ok` (NATS).
Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/live` → expected `200` (MinIO).
Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:4000/health/liveliness` → expected `200` (LiteLLM).
Run: `curl -s -u interview:interview http://localhost:5432 -o /dev/null` is not meaningful for postgres; instead verify via `docker compose exec postgres pg_isready -U interview` → expected `accepting connections`.
Run: `docker compose exec mongo mongosh --quiet --eval "db.adminCommand('ping').ok"` → expected `1`.

- [ ] **Step 6: Commit**

```bash
git add infra .env.example
git commit -m "feat(infra): docker-compose stack (postgres, mongo, minio, nats, litellm)"
```

---

### Task 4: Ruff, pre-commit, README

**Files:**
- Modify: `backend/pyproject.toml` (ruff lint/select config appended)
- Create: `.pre-commit-config.yaml`
- Create: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `ruff check .` and `ruff format --check .` pass from `backend/`; `pre-commit run --all-files` passes at repo root. README quickstart that later milestones extend.

- [ ] **Step 1: Append ruff lint rules to `backend/pyproject.toml`**

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

- [ ] **Step 2: Create `.pre-commit-config.yaml` at repo root**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-added-large-files
```

- [ ] **Step 3: Install and run pre-commit**

Run: `cd backend && uv run ruff check . && uv run ruff format .`
Expected: no lint errors; files reformatted if needed (re-run pytest after formatting: `uv run pytest -v` — expected 3 passed).

Run: `uv run pre-commit install && uv run pre-commit run --all-files`
Expected: all hooks pass (fixers may modify files once; re-run until clean, then include changes in commit).

- [ ] **Step 4: Create `README.md` at repo root**

```markdown
# InterviewCopilot

AI-powered interview preparation, simulation, and coaching platform for students.
Phase 1: text interviews. See `docs/design/` for the product and architecture documents,
and `docs/superpowers/specs/` for the current build spec.

## Quickstart (local, free stack)

Prerequisites: Python 3.13+, uv, Node 20+ (later milestones), Docker Desktop running.

1. `cp .env.example .env`
2. `cd infra && docker compose up -d` — starts Postgres, MongoDB, MinIO, NATS, LiteLLM
3. `cd backend && uv sync`
4. `uv run pytest` — backend tests
5. `uv run uvicorn app.main:app --reload` — API at http://localhost:8000 (docs at /docs)

## Layout

- `backend/` — FastAPI modular monolith
- `frontend/` — React web app (added in M2)
- `infra/` — docker-compose + LiteLLM config
- `docs/` — design docs, specs, plans
```

- [ ] **Step 5: Final M1 acceptance check**

Run: `cd backend && uv run pytest -v` → 3 passed.
Run: `cd infra && docker compose ps` → 5 services healthy.
Run: `curl -s http://localhost:8000/healthz` with server running → `{"status":"ok"}`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: ruff lint rules, pre-commit hooks, README quickstart"
```

---

## M1 Acceptance (from spec §14)

- [ ] Repo skeleton exists; `docker compose up` — all five services healthy
- [ ] FastAPI `/healthz` green (pytest + curl)
- [ ] ruff + pre-commit configured and passing
- [ ] All work committed with conventional commit messages
