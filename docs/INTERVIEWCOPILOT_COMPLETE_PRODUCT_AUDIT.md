# InterviewCopilot Complete Product Audit

**Date:** 2026-11-16  
**Scope:** Read-only audit (architecture, APIs, question quality, multi-discipline, onboarding, lifecycle, LLM, security, performance, uniqueness).  
**Constraint:** No product code or shared-data mutations. Live mutating API/lifecycle checks marked **NOT EXECUTED — DATA SAFETY RESTRICTION**.

### Evidence labels

| Label | Meaning |
|-------|---------|
| **Verified** | Confirmed by automated tests and/or code + matching tests in this audit pass |
| **Inspected only** | Static code/config inspection; no live confirmation |
| **NOT EXECUTED** | Blocked by data-safety rule or missing local infra (do not treat as product pass/fail) |

---

## A. Executive Summary

InterviewCopilot is a FastAPI + React product that coaches candidates via onboarding/vault, authored tracks/briefs, timed interview sessions (Strict/Guided), and async feedback. Dual stores (Postgres for durable domain state, Mongo for coach conversations / LLM logs / readiness cache) sit behind LiteLLM failover and a NATS feedback worker.

**Verdict in one line:** Core interview loop, auth, onboarding, tracks, and feedback are **implemented and largely verified by unit/e2e mocks**; multi-discipline support and readiness probes are **partial**; several APIs are **backend-only / orphaned from FE**; shared DB lifecycle and DB-backed integration suites were **not executed** this pass.

| Status | Count (approx) |
|--------|----------------|
| Working and verified | Auth cookies, healthz, question plan/policy unit paths, structured gateway unit paths, mocked interview e2e (submit/viewport/finish), FE stuck-turn Submit dock |
| Partially working | Multi-discipline (`domain_profile` + CS fallbacks), readiness (`/readyz` skips Mongo/S3), Dashboard open-sessions/assessments error UX, vault CRUD surface |
| Implemented but not verified | Most mutating interview/onboarding/vault/admin flows against shared DB |
| Broken / drift | Two `test_question_dedupe` mocks vs `structured_completion` call style (TypeError) |
| Not implemented / orphan FE | FE never calls `abort`, `goals/confirm`, `review/refresh`, `GET …/brief`, `POST /vault/items`, `dev/llm-check` |
| Not required | `dev/llm-check` (local-only) |

**Top P0 risks:** (1) `_ARRAY_CONCEPT_BANK` can inject DSA questions when `remaining_areas` is empty on non-CS tracks; (2) `/readyz` can report ready while Mongo/S3 are down; (3) Motor `get_mongo_db()` opens a client per Depends call outside lifespan.

---

## B. Architecture

**Evidence:** Inspected only (code + compose), except healthz unit tests.

```
FE (Vite/React) ──cookie JWT──► FastAPI /api/v1
                                 ├─ services (interview, onboarding, vault, feedback, …)
                                 ├─ agents (onboarding, question_plan, interviewer, track_creator,
                                 │          feedback_agent, assistance, session_pool, dedupe/quality)
                                 ├─ Postgres (users, tracks, briefs, sessions, turns, assessments)
                                 ├─ Mongo (onboarding_conversations, llm_call_logs, readiness_cache)
                                 ├─ NATS → feedback/track-authoring worker
                                 ├─ SeaweedFS/S3 (resume objects)
                                 └─ LiteLLM (Groq → NIM → Gemini)
```

| Layer | Primary paths | Notes |
|-------|---------------|-------|
| API | `backend/app/api/v1/*`, `main.py` | Mounted under `/api/v1`; `/healthz`, `/readyz` at root |
| FE contracts | `frontend/src/lib/api.ts` + pages | Thin `api()` helper; React Query call sites |
| Agents | `backend/app/agents/` | Interviewer owns turn decision + `apply_local_policy` |
| Dual state | SQLAlchemy models + `conversation_store.py` | Coach context / message idempotency in Mongo |
| Infra | `infra/docker-compose.yml`, `infra/litellm/config.yaml` | Failover declared in LiteLLM config |

**Disconnected / fragile pieces (Inspected only):**

1. **`/readyz`** probes Postgres, NATS, LiteLLM only — not Mongo or S3 (`main.py`).
2. **`get_mongo_db()`** creates a new `AsyncIOMotorClient` per call (`db/mongo.py`); lifespan holds one client on `app.state`, but Depends paths may not.
3. **Only one Mongo index** created at startup: unique `user_id` on `onboarding_conversations`.
4. **Question sourcing dual path:** deterministic `question_plan` + bank/pool vs improvised LLM turn + local policy + CS-leaning fallbacks.
5. **Onboarding dual path:** short-circuit / local reply rules vs full LLM coach (`onboarding` agent + service).
6. **FE orphans:** several authenticated routes exist with no UI caller (see §C).

---

## C. API Crosswalk

Authz baseline (**Inspected only**): `get_current_user` (HTTP-only access cookie JWT) on protected routes; `require_admin` email allow-list for `/admin/*`. Session ownership via `_owned_session` in `interview_service.py`.

Live curls that create/mutate rows: **NOT EXECUTED — DATA SAFETY RESTRICTION**.

### Auth (`/api/v1/auth`)

| Method | Path | Purpose | Authz | FE caller | Tests | Status |
|--------|------|---------|-------|-----------|-------|--------|
| GET | `/auth/google/url` | Start OAuth | Public | `SignInPage` (redirect) | `test_auth_flow` (DB) | Implemented; live OAuth **NOT EXECUTED** |
| GET | `/auth/google/callback` | OAuth callback, set cookies | Public + session | Browser redirect | same | Implemented; **NOT EXECUTED** live |
| POST | `/auth/refresh` | Rotate access | Refresh cookie | `authRefresh.ts` | same | Inspected + FE wired |
| POST | `/auth/logout` | Clear cookies | User | `AuthContext` | same | Inspected + FE wired |
| GET | `/auth/me` | Current user | User | `AuthContext`, `ProfilePage` | same | Inspected + FE wired |
| PATCH | `/auth/me` | Profile fields | User | `ProfilePage` | same | Implemented; mutate **NOT EXECUTED** |

### Onboarding (`/api/v1/onboarding`)

| Method | Path | Purpose | Authz | FE caller | Tests | Status |
|--------|------|---------|-------|-----------|-------|--------|
| POST | `/onboarding/chat` | Coach turn (`message_id` idempotent) | User | `OnboardingPage` | `test_onboarding*`, prompt rules | Partially verified (unit); live chat **NOT EXECUTED** |
| POST | `/onboarding/starter` | Starter prompt | User | `OnboardingPage` | onboarding tests | Same |
| GET | `/onboarding/state` | State + vault_items | User | `OnboardingPage` | onboarding tests | Inspected + FE |
| POST | `/onboarding/goals` | Goal discovery | User | `OnboardingPage` / `GoalDiscovery` | preparation tests | Mutate **NOT EXECUTED** |
| POST | `/onboarding/goals/confirm` | Confirm goals | User | **None (orphan)** | preparation tests | Implemented; no FE |
| POST | `/onboarding/complete` | Finish onboarding | User | `OnboardingPage` | onboarding tests | Mutate **NOT EXECUTED** |
| GET | `/onboarding/review` | Profile review | User | `DashboardPage` | `test_preparation_review` | Inspected |
| PATCH | `/onboarding/review` | Edit review | User | `DashboardPage` | same | Mutate **NOT EXECUTED** |
| POST | `/onboarding/review/refresh` | Regenerate review | User | **None (orphan)** | same | Implemented; no FE |
| POST | `/onboarding/review/start-recommended` | Create recommended track | User | Dashboard + Onboarding | same | Mutate **NOT EXECUTED** |

### Vault (`/api/v1/vault`)

| Method | Path | Purpose | Authz | FE caller | Tests | Status |
|--------|------|---------|-------|-----------|-------|--------|
| GET | `/vault/items` | List items | User | `StartInterviewModal` (also via onboarding state → `VaultSidebar`) | `test_vault` | Inspected |
| POST | `/vault/items` | Create item | User | **None (orphan)** | `test_vault` | Implemented; no FE create path |
| PATCH | `/vault/items/{id}` | Update | User | `VaultSidebar` | `test_vault` | Mutate **NOT EXECUTED** |
| DELETE | `/vault/items/{id}` | Delete | User | `VaultSidebar` | `test_vault` | Mutate **NOT EXECUTED** |
| POST | `/vault/resume` | Upload + extract | User | `OnboardingPage` | `test_resume*` | Mutate **NOT EXECUTED** |
| POST | `/vault/readiness` | Readiness score | User | `ReadinessPage` | `test_readiness` | Inspected; may hit LLM/cache |

### Tracks (`/api/v1/tracks`)

| Method | Path | Purpose | Authz | FE caller | Tests | Status |
|--------|------|---------|-------|-----------|-------|--------|
| POST | `/tracks` | Create track + brief authoring | User | `DashboardPage` | `test_tracks` | Mutate **NOT EXECUTED** |
| GET | `/tracks` | List | User | Dashboard, Readiness | same | Inspected |
| GET | `/tracks/{id}` | Track + brief | User | `TrackDetailPage` | same | Inspected |
| GET | `/tracks/{id}/brief` | Brief only | User | **None (orphan)** | same | Backend-only |
| DELETE | `/tracks/{id}` | Soft archive | User | `DeleteTrackDialog` | `test_track_archive` | Mutate **NOT EXECUTED** |
| POST | `/tracks/{id}/restore` | Restore | User | Dashboard | same | Mutate **NOT EXECUTED** |
| POST | `/tracks/{id}/reauthor-brief` | Re-author | User | TrackDetail | same | Mutate **NOT EXECUTED** |

### Interviews (`/api/v1` interviews router)

| Method | Path | Purpose | Authz | FE caller | Tests | Status |
|--------|------|---------|-------|-----------|-------|--------|
| GET | `/me/open-sessions` | All open sessions | User | `DashboardPage` | `test_open_sessions` | Inspected; thin FE error UI |
| GET | `/tracks/{id}/open-session` | Open for track | User | `StartInterviewModal` | same | Inspected |
| POST | `/tracks/{id}/close-empty-sessions` | Close empty | User | `StartInterviewModal` | interview tests | **NOT EXECUTED** (mutates) |
| POST | `/tracks/{id}/sessions` | Start session | User | `StartInterviewModal` | `test_interview*` | **NOT EXECUTED** |
| POST | `/sessions/{id}/abort` | Abort | User + ownership | **None (orphan)** | interview tests | Implemented; no FE |
| GET | `/sessions/{id}` | Session + turns | User + ownership | `InterviewPage` | interview tests | Verified via mocked e2e |
| POST | `/sessions/{id}/turns` | Submit answer | User + ownership | `InterviewPage` | interviewer/dedupe/plan units + e2e mock | Unit Verified; live **NOT EXECUTED** |
| POST | `/sessions/{id}/assistance` | Hint (Guided) | User + ownership | `InterviewPage` | `test_assistance` | Inspected |
| POST | `/sessions/{id}/complete` | Finish + enqueue feedback | User + ownership | Interview / Dashboard / Start modal | `test_complete_dispatch` | Mutate **NOT EXECUTED**; mocked e2e covers FE path |

### Feedback

| Method | Path | Purpose | Authz | FE caller | Tests | Status |
|--------|------|---------|-------|-----------|-------|--------|
| GET | `/sessions/{id}/report` | Feedback report | User | `ReportPage` | `test_feedback_*` | Inspected + e2e mock |
| GET | `/tracks/{id}/progression` | Progression | User | Start modal, TrackDetail | same | Inspected |
| GET | `/me/assessments` | Assessment rollup | User | Dashboard, Profile | `test_profile_and_assessments` | Inspected; thin FE error UI |
| GET | `/tracks/{id}/weaknesses` | Weak areas | User | Dashboard, Start modal, TrackDetail | `test_probe_and_weakness` | Inspected |

### Admin / Dev

| Method | Path | Purpose | Authz | FE caller | Tests | Status |
|--------|------|---------|-------|-----------|-------|--------|
| GET | `/admin/overview` | Metrics | Admin | `AdminOverviewPage` | `test_admin` | Inspected |
| GET | `/admin/users` | User list | Admin | `AdminUsersPage` | same | Inspected |
| GET | `/admin/users/{id}` | User detail | Admin | `AdminUserDetailPage` | same | Inspected |
| POST | `/dev/llm-check` | Local LLM smoke | `app_env==local` else 404 | **None** | — | Not required in product UI |

### App health

| Method | Path | Purpose | Tests | Status |
|--------|------|---------|-------|--------|
| GET | `/healthz` | Liveness | `test_healthz` | Working and verified (unit) |
| GET | `/readyz` | Dependency probe (PG/NATS/LiteLLM) | health-related | Partially working — Mongo/S3 omitted (**Inspected only**) |

---

## D. Question Quality

**Flow (Inspected only):** `question_plan` (duration-aware topics) → bank / pool opening (`session_pool`, brief `pool`) → `run_interviewer_turn` + `apply_local_policy` (subject progression, follow-up caps) → `question_dedupe` / local duplicate guards → fallback stems / banks.

| Concern | Finding | Evidence |
|---------|---------|----------|
| Plan enrichment | Duration and remaining areas drive topic list | `question_plan.py`; **Verified** `test_question_plan` |
| Local policy | Enforces progression / decision repair | `interviewer.apply_local_policy`; **Verified** interviewer engine / variety tests |
| Dedupe | Lexical + near-duplicate concept checks; CS-flavored examples in tests/banks | `question_dedupe.py`; partial — 2 integration-style tests **Broken** (mock signature) |
| Fallback bank | When area looks like “array” **or `remaining` empty**, `_ARRAY_CONCEPT_BANK` DSA stems are candidates | `interviewer.py` `_fallback_unique_question` — **P0** multi-discipline risk |
| Bank-first | Validated bank questions preferred before improvisation | Inspected in fallback + M9 bank fill tests |
| Prompts | Programming heuristics still present via `is_programming_brief` regex | `question_quality.py` |

**Verification this pass:** Offline unit suites for plan/quality/interviewer/session_variety/persona/eval included in the audit pytest batch (**101 passed** overall batch; see § test notes). Live interview quality sampling: **NOT EXECUTED**.

---

## E. Multi-Discipline Support

| Mechanism | Status | Notes |
|-----------|--------|-------|
| `domain_profile` on brief | Partially working | Authored via `track_creator` + `sanitize_domain_profile`; drives allowed types / mix |
| `active_profile` / `fallback_profile` | Inspected | Missing/invalid profile → regex programming vs “other” |
| `is_programming_brief` | Fragile | Subject/summary/topic regex — false positives/negatives possible |
| Vault-derived plan areas | Conditional | Merged into plan only when `use_resume` (`interview_service`) |
| Pool area match | Fragile | Exact/area-string matching in pool pick paths |
| FE `questionKind.ts` | Inspected | Coding workspace gating still heuristic |
| Array concept bank | **P0 gap** | Can fire for non-array tracks when `remaining_areas` empty |

**Tests:** `test_domain_profile` in audit batch (unit). Cross-discipline live sessions: **NOT EXECUTED**.

---

## F. Onboarding / Vault

| Area | Status | Evidence |
|------|--------|----------|
| Coach chat + starters | Partially working | FE wired; unit prompt/quality tests Verified; live LLM chat **NOT EXECUTED** |
| `message_id` idempotency | Inspected | Schema + service; good for client abort/retry |
| Coach context persistence | Inspected | Mongo `conversation_store` / `coach_context` |
| Topic lock / short replies | Inspected | Onboarding agent local rules + LLM path |
| Resume upload | Implemented, not live-verified | FE `POST /vault/resume`; S3 + extraction |
| Vault sidebar | Partially working | Items from `/onboarding/state`; PATCH/DELETE wired; **no FE POST /vault/items** |
| Goals confirm / review refresh | Backend only | Orphan routes |

---

## G. Interview Lifecycle

| Feature | Status | Evidence |
|---------|--------|----------|
| Start / resume open session | Implemented; live **NOT EXECUTED** | `StartInterviewModal` + open-session APIs |
| Submit answer | Working and verified (mocked e2e + units) | `InterviewPage` + turns API |
| Stuck turn `needsSubmitRetry` | Working and verified (code + prior e2e intent) | Submit dock remains when answer saved / eval failed |
| Pinned Submit / Next / Finish dock | Working and verified | Playwright viewport + smoke **9 passed** this pass |
| Finish & Exit | Working and verified (mocked e2e) | `finishExit.spec.ts` |
| Deadline display vs enforce | Partially working | FE display; backend deadline enforcement in service — live edge **NOT EXECUTED** |
| Abort session | Implemented; no FE | Orphan `POST …/abort` |
| `session.isError` UI | Gap | `InterviewPage` handles `isLoading` only — failed session fetch has no dedicated error panel (**Inspected**) |
| Dashboard open-sessions / assessments errors | Gap | No `isError` UI branches found (**Inspected**) |

---

## H. LLM Gateway

| Capability | Status | Evidence |
|------------|--------|----------|
| Shared HTTP client | Inspected | Warmed in lifespan; `gateway/llm.py` |
| Failover chain | Inspected | `infra/litellm/config.yaml`: Groq → NIM → Gemini; `num_retries: 0` (app owns backoff) |
| Structured JSON + repair | Working and verified (unit) | `structured.py`; `test_structured`, `test_gateway` |
| 429 / concurrency handling | Inspected + unit | Gateway tests; live provider stress **NOT EXECUTED** |
| Call logging | Inspected | Optional Mongo `llm_call_logs` |
| `dev/llm-check` | Local only | 404 outside `local` |

Production live provider calls that write product state: **NOT EXECUTED**.

---

## I. Security / Performance (qualitative)

**Security (Inspected only unless noted):**

- HTTP-only access/refresh cookies; `Secure` when `app_env != local`; `SameSite=lax` for OAuth return.
- Admin gated by `ADMIN_EMAILS` set membership (`require_admin`).
- Interview/feedback routes use ownership checks (`_owned_session` / user-scoped queries).
- Vault/resume scoped to current user in services (**Inspected**).
- Risk: logging may include prompt fragments in LLM logs — treat as PII-adjacent; redact in ops.
- Risk: `/dev/llm-check` unauthenticated beyond env gate — acceptable only if `local` never exposed.

**Performance / ops (Inspected only — no invented latency numbers):**

- `/readyz` false confidence if Mongo/S3 fail.
- Motor client-per-Depends vs lifespan client inconsistency.
- Thin Mongo indexing beyond onboarding `user_id`.
- Pool top-up and feedback are async (NATS/background) — good for request latency; failure modes need ops visibility.
- Compose vs app port defaults historically drifted — verify deploy docs against running compose (**Inspected** risk from inventory).

---

## J. Pending Items / Bugs / Gaps

| ID | Priority | Item | Path / area | Risk |
|----|----------|------|-------------|------|
| J1 | P0 | Array concept bank when `remaining` empty leaks DSA into other disciplines | `agents/interviewer.py` `_fallback_unique_question` | Wrong-subject questions |
| J2 | P0 | `/readyz` skips Mongo & object storage | `main.py` | Traffic to half-down stack |
| J3 | P1 | `get_mongo_db()` new Motor client per call | `db/mongo.py` | Connection churn / loop bugs |
| J4 | P1 | FE missing `session.isError` on InterviewPage | `InterviewPage.tsx` | Blank/stuck UI on fetch fail |
| J5 | P1 | Dashboard thin error UI for open-sessions & assessments | `DashboardPage.tsx` | Silent empty states |
| J6 | P1 | Orphan APIs (abort, goals/confirm, review/refresh, GET brief, POST vault items) | FE vs `api/v1` | Dead product surface / incomplete UX |
| J7 | P2 | `test_question_dedupe` mocks require positional `client`; production calls kwargs-only | `tests/test_question_dedupe.py` vs `interviewer.py` | CI false red; coverage gap |
| J8 | P2 | CS-heavy dedupe examples / programming regex bias | `question_dedupe.py`, `question_quality.py` | Weaker non-CS paraphrase control |
| J9 | P2 | Vault areas in plan only if `use_resume` | `interview_service.py` | Skills ignored unless flag |
| J10 | P2 | Exact area-string pool matching | session pool / interview service | Missed pool hits |
| J11 | P3 | Mongo indexes beyond conversations | lifespan | Scan cost as logs grow |
| J12 | P3 | Live lifecycle / auth OAuth / shared DB suites | — | **NOT EXECUTED** this audit |

---

## K. Unique Opportunities (grounded in existing architecture)

1. **Explainable evaluation** — Turn evaluations already carry coverage/gaps/rubric hooks; surface “why this score” in Guided mode using existing evaluator checks (**MVP:** FE render of current evaluation payload).
2. **Weakness-directed sessions** — `/weaknesses` + `focus_weak` already exist; make “fix this gap” a first-class dashboard CTA (**MVP**).
3. **Vault project defense** — Project vault details + `use_resume` plan merge can power project-deep-dive tracks without new storage (**MVP** with safer non-CS fallbacks).
4. **Persona pack** — Personas already selectable at start; productize consistent voice + scoring bias disclosure (**near-term**).
5. **Cross-discipline planner** — Extend `domain_profile` so plan/fallback banks are profile-keyed (replace array bank default) (**MVP differentiator**).
6. **Coach continuity** — Mongo coach_context can bridge onboarding → interview brief enrichment automatically (**later**).
7. **Admin/LLM cost lens** — `llm_call_logs` + admin overview can become cost/quality ops without new pipelines (**later**).
8. **Idempotent mobile-flaky chat** — `message_id` already supports retry UX; expand to interview turn client ids (**later**).

---

## L. Roadmap (P0 → P3)

1. **P0 — Discipline-safe fallbacks:** Gate `_ARRAY_CONCEPT_BANK` to programming/array profiles only; generic stems otherwise.
2. **P0 — Honest readiness:** Add Mongo (+ optional S3) checks to `/readyz`.
3. **P1 — FE resilience:** Session fetch error UI; Dashboard query error states; wire or deliberately hide orphan APIs (abort, vault create, review refresh).
4. **P1 — Mongo client lifecycle:** Prefer `request.app.state.mongo_db` in Depends; avoid per-call clients.
5. **P2 — Test hygiene:** Fix dedupe mocks (`client=None` default); restore CI signal.
6. **P2 — Multi-discipline hardening:** Profile-aware pool match; vault areas without requiring resume flag; reduce regex-only programming detection.
7. **P3 — Indexes & observability:** LLM log indexes; qualitative SLOs from existing logs (no fabricated targets here).
8. **Later — Product uniqueness:** Weakness CTA, explainable eval, persona packs (see §K).

*This audit does not implement the above.*

---

## M. Verdict

InterviewCopilot’s **spine is real**: auth cookies, onboarding/vault model, track briefs with domain profiles, planned interviews with local policy, feedback worker path, and a FE that can submit, recover stuck turns, and finish — confirmed where tests/mocks allow.

It is **not yet a verified multi-discipline production coach**: CS-leaning fallbacks, incomplete readiness probing, FE/API orphans, and unexecuted shared-DB lifecycle checks keep confidence bounded. Treat statuses as **Verified / Inspected / NOT EXECUTED** exactly as labeled; do not equate “implemented in code” with “proven on shared data.”

**Overall:** **Partially working → working for the core CS-leaning interview loop under test mocks; production multi-discipline and ops readiness need the P0/P1 items before claiming full product readiness.**

---

## Appendix: Test execution (this audit)

### Ran (safe / mocked)

| Suite | Result | Notes |
|-------|--------|-------|
| Focused pytest batch (plan, dedupe, quality, interviewer, domain_profile, gateway, structured, onboarding prompt/quality, session_variety, healthz, security, mode_validation, persona, eval_consistency) | **101 passed**, **1 skipped**, **20 failed**, **18 errors** | Failures/errors overwhelmingly **ConnectionRefused** to Postgres `:5433` / Mongo (test infra down) — environment, not claimed product regressions |
| `test_question_dedupe` (`falls_back`, `rejects_semantic_paraphrase`) | **2 failed** | `TypeError`: mock `structured_completion` requires positional `client`; production calls omit it | 
| Playwright `e2e/smoke`, `interviewViewport`, `finishExit` | **9 passed** | API-mocked; Chromium installed in agent environment for this run |

### NOT EXECUTED — DATA SAFETY RESTRICTION

- Live OAuth, chat, resume upload, track create, session create/turns/complete against shared DB  
- `close-empty-sessions`, abort, vault mutating CRUD, admin mutations  
- Seed/reset/purge, NATS purge, volume wipe  
- Any check that would insert/update/delete shared product rows  

### Infra note

Backend tests expect `interviewcopilot_test` on Postgres **:5433** (see test settings). When that stack is down, DB-backed suites error with connection refused — document as **Untested / blocked**, not as product failure.
