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

### Google sign-in (M2)

1. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`
   (Google Cloud Console → OAuth client (Web) → redirect URI
   `http://localhost:8000/api/v1/auth/google/callback`).
2. Start the API and open `http://localhost:8000/api/v1/auth/google/url` in a browser,
   complete consent — you land on "Signed in to InterviewCopilot".
3. `curl -s http://localhost:8000/api/v1/auth/me --cookie "ic_access=<value>"`.

### LLM gateway (M2)

1. Add `GROQ_API_KEY=` (free, console.groq.com) to `.env`, then
   `cd infra && docker compose up -d --force-recreate litellm` (pick up the key).
2. `curl -s -X POST http://localhost:8000/api/v1/dev/llm-check -H "Content-Type: application/json" -d '{"prompt":"Say hi in 5 words"}'`
   → returns the model's reply; the call is logged in Mongo `llm_call_logs`.
