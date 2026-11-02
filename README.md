# InterviewCopilot

AI-powered interview preparation, simulation, and coaching platform for students.
Phase 1: text interviews. See `docs/design/` for the product and architecture documents,
and `docs/superpowers/specs/` for the current build spec.

## Quickstart (local, free stack)

Prerequisites: Python 3.13+, uv, Node 20+ (later milestones), Docker Desktop running.

1. `cp .env.example .env` (repo root) and fill in your keys
2. `cd infra && docker compose --env-file ../.env up -d` — starts Postgres, MongoDB (host port **27018**), SeaweedFS (S3), NATS, LiteLLM.
   `--env-file ../.env` is required: compose otherwise reads `infra/.env` and would miss your API keys (LiteLLM would get no Groq key).
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
   `cd infra && docker compose --env-file ../.env up -d --force-recreate litellm` (pick up the key).
   Model: `openai/gpt-oss-120b` via Groq (the old `llama-3.3-70b-versatile` was retired by Groq).
2. `curl -s -X POST http://localhost:8000/api/v1/dev/llm-check -H "Content-Type: application/json" -d '{"prompt":"Say hi in 5 words"}'`
   → returns the model's reply; the call is logged in Mongo `llm_call_logs`.

### Onboarding & vault (M3)

With the API running and signed in via the browser flow above (you have an `ic_access` cookie):

- Chat with the Onboarding Agent: `curl -s -X POST http://localhost:8000/api/v1/onboarding/chat -H "Content-Type: application/json" --cookie "ic_access=<token>" -d '{"message":"I built a line-following robot"}'`
- See the vault: `curl -s http://localhost:8000/api/v1/vault/items --cookie "ic_access=<token>"`
- Upload a resume: `curl -s -X POST http://localhost:8000/api/v1/vault/resume --cookie "ic_access=<token>" -F "file=@resume.pdf"`

### Tracks & Interview Brief (M4)

- Create a topic track: `curl -s -X POST http://localhost:8000/api/v1/tracks -H "Content-Type: application/json" --cookie "ic_access=<token>" -d '{"track_type":"topic","subject":"Data Structures & Algorithms"}'` — the Track Creator Agent authors Brief v1.
- Role track with company+JD: `{"track_type":"company_jd","subject":"SDE Intern","company":"Acme","jd_text":"..."}`
- List tracks / open one: `GET /api/v1/tracks`, `GET /api/v1/tracks/{id}`, `GET /api/v1/tracks/{id}/brief`.

### Interviews (M5)

- Start a Strict interview on a track: `curl -s -X POST http://localhost:8000/api/v1/tracks/{track_id}/sessions --cookie "ic_access=<token>" -H "Content-Type: application/json" -d '{"mode":"strict"}'` → returns the first question.
- Answer: `curl -s -X POST http://localhost:8000/api/v1/sessions/{session_id}/turns --cookie "ic_access=<token>" -H "Content-Type: application/json" -d '{"answer":"..."}'` → returns the evaluation and the next question, or `completed: true`.
- Transcript / resume after restart: `GET /api/v1/sessions/{session_id}` (state lives in Postgres rows).

### Feedback & progression (M6)

1. Start the feedback worker in a second terminal: `cd backend && uv run python -m app.workers.feedback_worker`
2. Complete an interview — the worker generates the report asynchronously.
3. Read it: `curl -s http://localhost:8000/api/v1/sessions/{session_id}/report --cookie "ic_access=<token>"`
4. Track progression (Guided unlocks after 3 struggling strict attempts): `curl -s http://localhost:8000/api/v1/tracks/{track_id}/progression --cookie "ic_access=<token>"`
5. Backlog healing (process sessions with missing reports, no NATS needed): `uv run python -m app.workers.feedback_worker --catch-up`
