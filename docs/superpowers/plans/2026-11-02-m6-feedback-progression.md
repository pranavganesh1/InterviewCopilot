# InterviewCopilot M6 — Feedback & Progression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Feedback Agent — agent #4 of 4 — runs asynchronously after each interview (NATS JetStream job): extracts per-question evidence, produces an evidence-based feedback report, and the progression policy updates per-track state so Guided mode unlocks after 3 struggling strict attempts.

**Architecture:** On session completion the API publishes a `feedback.jobs` event (JetStream stream `FEEDBACK`, durable consumer `feedback-worker`). A worker process (`python -m app.workers.feedback_worker`) consumes it and calls `feedback_service.process_session_feedback` — the same function tests call directly. The Feedback Agent is a LangGraph graph with two nodes (`extract_evidence` → `assess`); per LLD invariant 11 the **agent never owns the state transition** — `progression_policy.py` decides Guided unlock from report aggregates. Reports are one-per-session (JSONB, MVP shape of the LLD schema; deviation recorded in spec). New dependency: `nats-py`.

**Tech Stack:** nats-py (new); existing stack otherwise.

**Spec:** `docs/superpowers/specs/2026-11-02-interviewcopilot-v1-build-design.md` (M6 row of §14) + `docs/design/LLD/04_Assessment_Feedback/` (schemas, progression_policy invariants).

## Global Constraints

- Same as M1–M5. Tests hit `interviewcopilot_test` (migrate BOTH DBs).
- Count only completed STRICT sessions for progression (invariant 1–3); per-track state (invariant 10); UNLOCKED is permanent (invariant 8).

---

### Task 1: FeedbackReport + ProgressionState models and migration

**Files:**
- Create: `backend/app/models/feedback.py`
- Modify: `backend/alembic/env.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_feedback_models.py`

**Interfaces:**
- `app.models.feedback.FeedbackReport` — `id`, `session_id` (FK sessions CASCADE, **unique**), `track_id` (index), `user_id` (index), `content` (JSONB), `created_at`.
- `app.models.feedback.ProgressionState` — `id`, `track_id` (FK tracks CASCADE, unique), `strict_completed: int` default 0, `guided_state: str` default `LOCKED` (`LOCKED`|`UNLOCKED`), `updated_at`.

Test: session → report roundtrip; progression defaults. Run migration for dev AND test DBs. Extend conftest cleanup (delete reports, progression states before sessions).

Commit: `feat(backend): feedback report and progression state models`.

---

### Task 2: Feedback Agent + feedback service + progression policy

**Files:**
- Create: `backend/app/agents/feedback_agent.py`, `backend/app/services/feedback_service.py`, `backend/app/services/progression_policy.py`
- Modify: `backend/app/core/config.py` (`guided_unlock_after_attempts: int = 3`)
- Test: `backend/tests/test_feedback_service.py`

**Interfaces:**
- `app.agents.feedback_agent.QuestionEvidence` — `turn_index: int`, `coverage: Literal["none","partial","good","excellent"]`, `observation: str`, `evidence_excerpt: str` (verbatim quote from the answer; "" if none).
- `app.agents.feedback_agent.AssessedCompetency` — `competency_name: str`, `assessment_status: Literal["ASSESSED","PARTIALLY_ASSESSED","NOT_ASSESSED","INSUFFICIENT_EVIDENCE"]`, `level: Literal["weak","developing","solid","strong"] | None`, `observation: str`, `confidence: Literal["HIGH","MEDIUM","LOW"]`.
- `app.agents.feedback_agent.FeedbackReportContent` — `report_version: int = 1`, `session_mode: Literal["strict","guided"]`, `summary_overview: str`, `coverage_status: Literal["COMPLETE","PARTIAL","MINIMAL"]`, `question_assessments: list[QuestionEvidence]`, `competency_assessments: list[AssessedCompetency]`, `strengths: list[str]`, `improvement_areas: list[str]`, `unassessed_topics: list[str]`, `recommendations: list[str]`.
- `build_feedback_graph(turn_runner=...)` — nodes `extract_evidence` (per-QA evidence) → `assess` (aggregate).
- `app.services.feedback_service.process_session_feedback(db, session_id) -> dict` — loads session+turns+brief (skips non-completed sessions: returns `{"skipped": ...}`), runs graph, upserts report, applies progression policy (strict sessions only), returns `{"report": ..., "progression": ...}`.
- `app.services.progression_policy.apply_progression(db, track_id, report_content, session_mode) -> dict` — increments `strict_completed` for strict sessions; when `strict_completed >= guided_unlock_after_attempts` and the last-3 aggregate shows struggle (majority of assessed levels in {"weak","developing"}) → `guided_state="UNLOCKED"` (permanent; never re-locks).

- [ ] **Step 1: Failing tests** — mocked agent outputs; assert report row exists with correct content; three weak strict sessions → `UNLOCKED`; strong sessions → stays `LOCKED`; guided sessions never increment the counter; second processing run replaces (not duplicates) the report.

- [ ] **Step 2: Implement → suite green → commit** `feat(backend): feedback agent, report pipeline, guided-unlock progression policy`

---

### Task 3: NATS publisher + worker process

**Files:**
- Add dep: `uv add nats-py`
- Create: `backend/app/workers/__init__.py`, `backend/app/workers/feedback_worker.py`, `backend/app/services/events.py`
- Modify: `backend/app/services/interview_service.py` (publish on completion), `backend/app/core/config.py` (`nats_url` exists? it does: `NATS_URL` in .env — add `nats_url` field if missing)

**Interfaces:**
- `app.services.events.publish_feedback_job(session_id, track_id, user_id) -> None` — ensures stream `FEEDBACK` (subjects `feedback.jobs`), publishes JSON event `{event_id, event_type: "session.feedback.requested", job_id, session_id, track_id, user_id, occurred_at}`; failures are logged, never raised (interview must not fail because feedback dispatch failed — the worker also has a catch-up scan).
- `app.workers.feedback_worker.main()` — connects, durable pull consumer `feedback-worker` on `feedback.jobs`, calls `process_session_feedback` for each event (loading its own DB session), `ack()` on success, `nak()` on failure, `max_deliver=3`. Also a `--catch-up` mode that scans completed sessions without reports (self-healing path, no NATS needed).
- Completion paths (`submit_answer` completed branch + `complete_session`) fire `publish_feedback_job` in a background task (`asyncio.create_task`) so the HTTP response stays fast.
- Worker runs via: `cd backend && uv run python -m app.workers.feedback_worker`.

- [ ] Implement → compile/import smoke test → commit `feat(backend): nats feedback job publisher and worker process`

---

### Task 4: Report + progression routes

**Files:**
- Modify: `backend/app/services/feedback_service.py` (get_report, get_progression helpers)
- Create/modify: `backend/app/api/v1/feedback.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_feedback_routes.py`

**Interfaces:**
- `GET /api/v1/sessions/{session_id}/report` → report content + id/created_at (404 until the worker has produced it; 404 for other users).
- `GET /api/v1/tracks/{track_id}/progression` → `{"track_id", "strict_completed", "guided_state"}`.
- Tests: route-level with mocked processing (or direct service writes), auth + 404 edges.

- [ ] Tests first → implement → suite green → commit `feat(backend): feedback report and progression routes`

---

### Task 5: README, live end-to-end acceptance, push

- [ ] README M6 section: run worker (`uv run python -m app.workers.feedback_worker`), then `GET /sessions/{id}/report`, `GET /tracks/{id}/progression`.
- [ ] Spec deviation note: MVP report trims LLD meta-fields (`profile_version_id`, `source_integrity`, `assistance_summary`); evidence simplified to per-question observations with excerpts.
- [ ] **Live acceptance:** start worker in background → complete a strict session via API against a real track → poll `GET /sessions/{id}/report` until ready → verify competency assessments + recommendations → run two more weak sessions → `GET /tracks/{id}/progression` shows `strict_completed: 3` and `guided_state: UNLOCKED`.
- [ ] Full suite + lint → commit → push.

---

## M6 Acceptance (from spec §14)

- [ ] Session completion triggers NATS job → feedback report viewable (real LLM)
- [ ] Progression updates; Guided unlocks per policy after 3 struggling strict attempts
- [ ] Suite green; pushed
