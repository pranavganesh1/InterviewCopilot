# InterviewCopilot M11 — Admin Analytics, Cost Attribution & Time-Aware Pacing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every LLM token is attributed to a user/track with an estimated dollar cost; an admin portal (role-gated by `ADMIN_EMAILS`) shows global and per-user analytics (time spent, topics, cost, performance); interviews become time-aware — the agent paces by `minutes_remaining`, covers high-value areas by ~70% time, and wraps up ~5 min early; durations gain a 45-min preset plus custom input.

**Architecture:** Pricing table lives in `app/gateway/pricing.py` (editable dict, labeled estimates). `chat_completion` gains an optional `meta` dict (user_id/track_id/session_id) — persisted into Mongo `llm_call_logs` with `estimated_cost_usd`. Callers thread meta from their context. Admin access = `ADMIN_EMAILS` env (comma-separated Google emails) checked in a `require_admin` dependency. Admin analytics read Mongo aggregations (llm_call_logs) + Postgres rollups (sessions/tracks/reports). Admin UI = `/admin` section in the existing app, server-gated (403 hides it). Time pacing: `question_plan` slots sized from duration; interviewer payload gains `plan_progress`; prompts gain wrap-up rules targeting a 5-minute buffer; presets 30/45/60/90/120/180 + custom (15–240).

**Tech Stack:** No new dependencies.

**Spec:** user decisions of 2026-11-05 (ADMIN_EMAILS, /admin in-app, costs hidden from users, list-price estimates).

## Global Constraints

- Same as M1–M9. Tests hit `interviewcopilot_test`. Candidates never see token/cost numbers.
- Cost figures are ESTIMATES against public list prices, editable in `pricing.py`.
- Admin gating is server-side (403); the UI only hides what the server already blocks.

---

### Task 1: Pricing table + gateway cost/meta logging

**Files:**
- Create: `backend/app/gateway/pricing.py`
- Modify: `backend/app/gateway/llm.py`
- Test: `backend/tests/test_pricing.py`

**Interfaces:**
- `pricing.py`: `estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float` — matches model by substring against a `_PRICES` dict (per-1M input/output USD, dated comment); unknown models price at 0 with a log warning.
- `chat_completion(..., meta: dict | None = None)`: stores `meta` fields (`user_id`, `track_id`, `session_id`) + `estimated_cost_usd` into `llm_call_logs`.

- [ ] **Step 1: Failing test** (`backend/tests/test_pricing.py`)

```python
from app.gateway.pricing import estimate_cost_usd


def test_known_model_cost():
    cost = estimate_cost_usd("groq/openai/gpt-oss-120b", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost > 0
    cost2 = estimate_cost_usd("groq/openai/gpt-oss-120b", 2_000_000, 0)
    assert cost2 != cost  # input/output prices differ


def test_unknown_model_prices_zero():
    assert estimate_cost_usd("mystery/model", 1000, 1000) == 0.0
```

- [ ] **Step 2: Implement → green → commit** `feat(backend): model pricing table + per-call cost estimation`

### Task 2: Thread meta through all LLM callers

**Files:**
- Modify: `app/services/onboarding_service.py`, `app/services/track_service.py`, `app/services/interview_service.py`, `backend/app/workers/feedback_worker.py` (via feedback_service)
- Pattern: each agent-facing service already knows user/track/session — pass `meta={"user_id": ..., "track_id": ..., "session_id": ...}` into `structured_completion`/`chat_completion` (which forwards to `chat_completion`'s meta).
- Note: `structured_completion` gains `meta: dict | None = None` pass-through.
- [ ] Update callers → `uv run pytest -q` green (mocked runners unaffected) → commit `feat(backend): attribute every llm call to user/track/session`

### Task 3: Admin gate + overview + user rollups

**Files:**
- Modify: `backend/app/core/config.py` (`admin_emails: str = ""`), new `backend/app/api/deps.py` addition `require_admin`
- Create: `backend/app/api/v1/admin.py`, `backend/app/services/admin_service.py`
- Modify: `backend/app/main.py` (register)
- Test: `backend/tests/test_admin.py` (403 non-admin; overview/user rollups with seeded Mongo+PG data)

**Interfaces:**
- `require_admin`: 403 unless `current_user.email` in `settings.admin_emails` (comma-split, lower-cased).
- `GET /admin/overview` → `{users, tracks, interviews_completed, interview_minutes, tokens_in, tokens_out, estimated_cost_usd, by_day: [{day, calls, tokens, cost}], by_model: [...]}` (last 30d window for by_day/by_model; totals all-time).
- `GET /admin/users` → `[{id, email, name, tracks, interviews, minutes, est_cost_usd, avg_coverage}]`
- `GET /admin/users/{id}` → `{user, tracks: [...], sessions: [{id, mode, status, minutes, started}], cost_usd, reports: [{session_id, coverage_status}]}`

- [ ] Tests first (seed user + llm_call_logs in Mongo via mongomock? No — admin tests use the real test Mongo via conftest pattern; seed via direct inserts) → implement → green → commit `feat(backend): admin gate, overview and per-user analytics`

### Task 4: Admin frontend

**Files:**
- Modify: `frontend/src/App.tsx` (`/admin` route), `frontend/src/components/AppHeader.tsx` (Admin link — visible only when `/auth/me` returns admin flag; simplest: backend `GET /auth/me` gains `is_admin: bool`)
- Create: `frontend/src/pages/AdminOverviewPage.tsx`, `frontend/src/pages/AdminUsersPage.tsx`, `frontend/src/pages/AdminUserDetailPage.tsx`
- Modify: `backend/app/api/v1/auth.py` — `/auth/me` gains `is_admin`

- [ ] Implement (plain Tailwind tables, same style) → build green → commit `feat(web): admin overview, users and user-detail pages`

### Task 5: Time-aware pacing + duration UX

**Files:**
- Modify: `backend/app/agents/question_plan.py` (N slots derived from duration: `slots = max(4, duration_minutes // 4)`), `backend/app/agents/interviewer.py` (pacing prompt rules: target wrap-up at `duration_minutes - 5`; by 70% time, cover the highest-importance remaining areas), `backend/app/services/interview_service.py` (pass plan progress: slots_used/total)
- Modify: `frontend/src/pages/TrackDetailPage.tsx` (presets 30/45/60/90/120/180 + custom minutes input 15–240)
- Test: `backend/tests/test_question_plan.py` (N scales with duration), existing interviewer tests green

- [ ] Test first → implement → green → commit `feat: time-aware pacing with 5-min buffer; duration presets + custom`

### Task 6: Verification + push

- [ ] Full suite + lint + build + e2e; live: track creation with bank, timed session start with plan, admin endpoints as ADMIN_EMAILS user
- [ ] README M11 note; push; PR

## Acceptance

- [ ] Every LLM call attributable (user/track/session) with estimated cost
- [ ] Admin portal: overview + per-user analytics, 403 for non-admins, costs hidden from candidates
- [ ] 45-min preset + custom durations; agent paces and wraps up ~5 min early
