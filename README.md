# InterviewCopilot

AI-powered interview preparation, simulation, and coaching platform for students.
Phase 1: text interviews. See `docs/design/` for the product and architecture documents,
and `docs/superpowers/specs/` for the current build spec.

## Quickstart (local, free stack)

Prerequisites: Python 3.13+, uv, Node 20+ (later milestones), Docker Desktop running.

1. `cp .env.example .env`
2. `cd infra && docker compose up -d` — starts Postgres, MongoDB, SeaweedFS (S3), NATS, LiteLLM
3. `cd backend && uv sync`
4. `uv run pytest` — backend tests
5. `uv run uvicorn app.main:app --reload` — API at http://localhost:8000 (docs at /docs)

## Layout

- `backend/` — FastAPI modular monolith
- `frontend/` — React web app (added in M2)
- `infra/` — docker-compose + LiteLLM config
- `docs/` — design docs, specs, plans
