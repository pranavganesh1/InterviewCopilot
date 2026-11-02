# InterviewCopilot v1 — Build Design (Spec)

**Date:** 2026-11-02
**Status:** Approved by product owner — implementation ready
**Baseline documents:** `docs/design/` (Product Overview v0.1, HLD v0.2, Member 1–4 LLDs, Member 4 modular LLD)

---

## 1. Goal

Build the first end-to-end working version of InterviewCopilot: a student signs in, completes onboarding (resume + conversational Candidate Context Vault), creates a Preparation Track, completes a text Strict Interview, and receives an evidence-based feedback report with progression state. Architecture follows HLD v0.2 faithfully; agent-level detail follows the Member LLDs.

## 2. Constraints and key decisions

| Decision | Value | Consequence |
|---|---|---|
| Builders | Product owner + AI, sequential | No parallel team split; milestone order below is the build order |
| Product class | Startup MVP | Real auth, env-based secrets, migrations, structured logging from day one |
| Budget | $0 | All infra local via Docker (free images); LLMs on free tiers; no paid services in M1–M7 |
| v1 scope | Phase 1 text interviews | Turn-by-turn chat POST; no streaming, no voice |
| Topology | Faithful HLD build | PostgreSQL + MongoDB + MinIO + NATS JetStream + LiteLLM proxy + LangGraph agents |
| Auth | Google OAuth only for v1 | Apple sign-in deferred (paid dev account); email/password is a later add-on |

## 3. Repository layout

```
InterviewCopilot/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers (/api/v1)
│   │   ├── core/         # settings, security, logging
│   │   ├── db/           # Postgres session, Mongo client, MinIO client
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # domain services (candidates, tracks, interviews, feedback)
│   │   ├── agents/       # LangGraph graphs (onboarding, track_creator, interviewer, feedback)
│   │   ├── tools/        # Agent Tool Layer (backend-enforced state mutations)
│   │   ├── gateway/      # LLM gateway client (LiteLLM proxy)
│   │   ├── workers/      # NATS JetStream consumers
│   │   └── main.py
│   ├── alembic/          # migrations
│   ├── tests/
│   └── pyproject.toml
├── frontend/             # React 19 + Vite + TypeScript + Tailwind
├── infra/
│   ├── docker-compose.yml
│   └── litellm/config.yaml
├── docs/
│   ├── design/           # existing HLD/LLD/product docs (source of truth)
│   └── superpowers/specs/  # this spec
└── .env.example          # committed; real .env git-ignored
```

## 4. Infrastructure (docker-compose)

| Service | Image | Purpose |
|---|---|---|
| postgres | `postgres:16` | Authoritative application state |
| mongo | `mongo:7` | Conversations, track memory, question history, LLM call logs |
| seaweedfs | `chrislusf/seaweedfs` | S3-compatible storage: resume uploads (future audio). *(Deviation from the original MinIO choice: MinIO removed its images from Docker Hub in 2025 and quay.io blocked anonymous pulls in this environment; SeaweedFS exposes the same S3 API contract on host port 9000.)* |
| nats | `nats:2` + JetStream | Async feedback jobs and events |
| litellm | `ghcr.io/berriai/litellm` | LLM gateway proxy (Groq primary, Gemini fallback) |

All services get healthchecks; persistent volumes; single `.env` (git-ignored) generated from `.env.example`.

## 5. Backend

- FastAPI (async), modular monolith. One codebase, two processes: API server and worker (NATS consumer).
- SQLAlchemy 2.0 async + Alembic for Postgres; Motor (async) for Mongo; boto3/S3 client for MinIO.
- Pydantic v2 settings from environment; structlog JSON logs with request IDs.

## 6. Auth

- Google OAuth 2.0 (OIDC): frontend gets auth URL → Google consent → backend callback verifies `id_token` → upserts user → issues backend-owned JWT pair (access ~15 min, refresh ~30 days) in httpOnly Secure cookies.
- `users` table: id, google_sub, email, name, created_at.
- Auth layer abstracted behind an interface so email/password can be added later without rework.

## 7. LLM Gateway

- **All** agent LLM traffic goes through the LiteLLM proxy container; backend authenticates with an internal API key.
- Model groups (free tiers, no credit card):
  - `interview-chat`: `groq/llama-3.3-70b-versatile` primary → `gemini/gemini-2.0-flash` fallback
  - `structured-json`: same models with JSON mode for schema-validated outputs
- Timeouts, 2 retries, automatic fallback; call metadata (model, latency, token counts, prompt hash — not full prompts) logged to Mongo `llm_call_logs`.
- Provider swap or upgrade later is a config-only change in `infra/litellm/config.yaml`.

## 8. Agents (LangGraph)

Four graphs; **the Member LLD documents are the source of truth for node-level detail**:

1. **Onboarding Agent** — conversational intake producing structured vault items (projects, internships, skills, achievements, education); resume upload → MinIO → PDF text extraction → structured merge into vault.
2. **Track Creator Agent** — preparation objective (topic / role / JD) → preparation plan + competency coverage + versioned Interview Brief.
3. **Interviewer Agent** — per-session state machine: question plan from Brief + per-track question history → ask → evaluate answer → bounded adaptive follow-ups → next question. Strict mode (no aids). Guided mode (hint ladder: nudge → clue → explanation) gated by progression policy.
4. **Feedback Agent** — NATS-triggered job: per-Q&A evidence extraction → competency assessment (only assessed topics scored) → feedback report → progression decision (3 strict attempts rule gates Guided unlock).

Shared rules: LangGraph Postgres checkpointer for crash recovery; structured outputs validated against JSON schemas with bounded repair retries; agents mutate state only via the Agent Tool Layer and reach LLMs only via the gateway.

## 9. Data ownership

- **PostgreSQL (authoritative):** users, vault_items, tracks, interview_briefs (versioned), interview_sessions, session_turns, evidence_items, competency_assessments, feedback_reports, progression_state, question_asked_history — plus LangGraph checkpointer tables (infrastructure, created by the library).
- **MongoDB (documenty):** onboarding conversations, track_memory, raw session threads, llm_call_logs.
- **MinIO:** resumes, future audio artifacts.
- Field-level schemas follow the Member LLD docs; conflicts are reconciled in the implementation plan, not silently.

## 10. API surface (v1, REST under `/api/v1`)

- `auth`: GET /auth/google/url · GET /auth/google/callback · POST /auth/refresh · POST /auth/logout · GET /auth/me
- `onboarding/vault`: POST /onboarding/chat · GET /onboarding/state · POST /vault/resume · GET/POST /vault/items
- `tracks`: POST /tracks · GET /tracks · GET /tracks/{id} · GET /tracks/{id}/brief
- `interviews`: POST /tracks/{id}/sessions · GET /sessions/{id} · POST /sessions/{id}/turns · POST /sessions/{id}/complete
- `feedback`: GET /sessions/{id}/report · GET /tracks/{id}/progression
- `ops`: GET /healthz · GET /readyz

## 11. Frontend

React 19 + Vite + TypeScript + Tailwind, React Router, TanStack Query. MVP screens: Sign-in, Onboarding chat + resume upload, Dashboard (tracks), Track detail, Interview session chat, Feedback report. Turn-by-turn POST per answer; streaming (SSE) deferred.

## 12. Reliability and observability

structlog JSON logging with request IDs; gateway timeouts/retries/fallback; JetStream durable consumers with ack/nak/retry and max-delivery dead-lettering; Alembic migrations; /healthz + /readyz with compose healthchecks. Prometheus/Grafana dashboards deferred beyond v1.

## 13. Testing

- pytest + pytest-asyncio; integration tests against dockerized Postgres/Mongo (compose test profile).
- Fake LLM gateway for unit tests of services and graph nodes.
- One scripted end-to-end happy path (onboard → track → strict interview → feedback report) using recorded LLM responses.
- Playwright browser smoke tests after the frontend milestone; vitest for critical frontend components.

## 14. Milestones and acceptance criteria

| # | Milestone | Done when |
|---|---|---|
| M1 | Scaffold & infra | Repo skeleton; `docker compose up` all services healthy; FastAPI /healthz green; ruff + pre-commit configured; committed |
| M2 | Auth & gateway | Google sign-in works end-to-end in browser; gateway chat completion round-trip succeeds and is logged |
| M3 | Onboarding & vault | Onboarding conversation produces vault items; resume upload → extracted text → vault entries visible |
| M4 | Tracks & brief | Topic/role track created; Interview Brief v1 generated and versioned |
| M5 | Interview engine | Full Strict text interview with adaptive follow-ups; turns persisted; session recovers after backend restart |
| M6 | Feedback & progression | Session completion triggers NATS job → feedback report viewable; progression updates; Guided unlocks per policy |
| M7 | Frontend & E2E | Full happy path in browser; scripted E2E green |
| M8 | Deployment | Live free-tier URL with documented trade-offs (free tiers sleep/limit; options compared at this point) |

## 15. What the product owner provides (per milestone)

- **M1:** start Docker Desktop.
- **M2:** free Groq API key; Google OAuth client ID + secret (guided setup, ~5 min); optional Gemini key for fallback.
- **M8:** choice among free hosting options.

## 16. Out of scope for v1

Voice interviews (ASR/TTS), Apple sign-in, email/password auth, streaming UI, coding execution sandbox, company research beyond supplied JD text, payments, admin panel, mobile apps, multi-region deployment.

## 17. References

- `docs/design/InterviewCopilot_High_Level_Design_v0.2.md` — architecture baseline
- `docs/design/InterviewCopilot_Member1..4_LLD.md` + `docs/design/LLD/04_Assessment_Feedback/` — module-level source of truth
- `docs/design/InterviewCopilot_Product_Overview_and_User_Journey.md` — product behavior and policy (Strict/Guided rules)
