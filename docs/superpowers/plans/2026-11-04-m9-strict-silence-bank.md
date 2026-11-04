# InterviewCopilot M9 — Strict Silence & Question Bank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strict interviews show zero live feedback (all evaluation stays server-side and lands in the report); Guided interviews show live evaluation chips + the assistance ladder; the Track Creator now authors a **validated question bank** (15–18 questions, deduped + quality-judged with bounded repair) stored inside the versioned Interview Brief, and the Interviewer draws from it before improvising.

**Architecture:** The bank lives in `InterviewBriefContent.question_bank` (versioned with the brief — no new tables). The Track Creator's authoring graph gains a `build_bank` node after `author`: generation → validation pass (`question_dedupe` + LLM quality judge returning accept/reject+reasons) → one bounded regeneration round for rejects (≤2 attempts; the bank always ships with whatever survives). The Interviewer's payload gains `question_bank` + `used_bank_questions`; its prompt and `apply_local_policy` prefer an unused bank question matching the current/next area before improvising; dedupe still applies. Frontend: `InterviewPage` gates evaluation chips on `mode === "guided"`; `TrackDetailPage` gains a collapsed bank section.

**Tech Stack:** No new dependencies. No new tables. No new keys.

**Spec:** user-approved design of 2026-11-04 (strict silence, guided live evaluation, LLM-only validated bank, no internet).

## Global Constraints

- Same as M1–M7.5. Tests hit `interviewcopilot_test`. E2E must stay hermetic.
- Strict UI must show NO evaluation data; Guided shows chips + assistance.
- Bank generation must NEVER block or fail track creation (fallback: ship without bank).

---

### Task 1: Strict-silence / Guided-evaluation UI split

**Files:**
- Modify: `frontend/src/pages/InterviewPage.tsx` (chips render only when `session.mode === "guided"`)
- Modify: `frontend/e2e/smoke.spec.ts` (existing strict interview test: assert evaluation chips are NOT visible; add a guided variant that asserts they ARE)

**Interfaces:** none new — `Turn.evaluation` stays in the API contract for both modes (the Feedback Agent consumes it; only display changes).

- [ ] Step 1: Update `InterviewPage` — evaluation chip block renders `{session.data?.session.mode === "guided" && evaluation && (...)}`
- [ ] Step 2: Update e2e — strict test asserts `page.getByText("partial")` NOT visible after answering; add guided-mode test (mock session with `mode: "guided"`) asserting the chip IS visible
- [ ] Step 3: build + full e2e green → commit `feat(web): strict interviews show no live evaluation; guided shows chips`

### Task 2: Question bank generation with validation loop

**Files:**
- Modify: `backend/app/agents/track_creator.py` — `BankQuestion` pydantic (`area`, `question`, `difficulty: Literal["foundational","intermediate","advanced"]`, `type: Literal["coding","conceptual","behavioral"]`, `expected_answer_sketch`); `InterviewBriefContent.question_bank: list[BankQuestion]` (default empty); `build_track_creator_graph` gains `build_bank` node after `author`; BANK_SYSTEM_PROMPT (15–18 questions across areas, distinct objectives, difficulty spread); validation pass = `question_dedupe.is_duplicate_question` pairwise + `structured_completion` quality judge (`BankVerdict: {verdicts: [{index, accept: bool, reason}]}`); one bounded regeneration round (max 2 attempts) re-asking ONLY for rejected indices; injectable turn-runner pattern preserved
- Modify: `backend/app/services/track_service.py` — pass bank through into brief content (it lands inside `content` automatically via the authoring result)
- Test: `backend/tests/test_question_bank.py` — mocked runners: happy path (bank present, no duplicates, ≥8 questions), judge rejects some → regenerated round happens, judge rejects twice → partial bank ships, generation crash → track still created with empty bank

- [ ] Test first → implement → suite green → commit `feat(backend): validated question bank in interview brief`

### Task 3: Interviewer consumes the bank

**Files:**
- Modify: `backend/app/services/interview_service.py` — payload gains `question_bank` (from brief content) and `used_bank_questions` (transcript questions matched to bank entries); `_decide` passes them
- Modify: `backend/app/agents/interviewer.py` — STRICT/GUIDED prompts gain bank rules ("prefer the next UNUSED bank question matching the current or next area; bank questions are pre-validated — use them verbatim; improvise only for adaptive follow-ups or when no suitable unused bank question exists"); `apply_local_policy`/`decision_violation` treat bank questions as always-acceptable (skip dedupe rejection for verbatim bank questions); tests extend `_setup_track_with_brief` mocks with banks
- Test: `backend/tests/test_interview.py` — mocked runner asserting the next question comes from the bank; bank questions never flagged as duplicates

- [ ] Test first → implement → suite green → commit `feat(backend): interviewer draws from validated question bank`

### Task 4: Track detail bank UI

**Files:**
- Modify: `frontend/src/lib/api.ts` (`BriefContent.question_bank`), `frontend/src/pages/TrackDetailPage.tsx` (collapsed `<details>` "Question bank (N questions)" listing area, difficulty chip, type, question text)
- Modify: `frontend/e2e/smoke.spec.ts` (mock brief with bank; assert section renders)
- [ ] Implement → build + e2e green → commit `feat(web): question bank section on track detail`

### Task 5: Live verify + README + push

- [ ] Live: create a new topic track → brief v1 contains a bank → strict interview draws from bank with zero live feedback → report still populated
- [ ] README M9 note; push; PR

## Acceptance

- [ ] Strict: zero live evaluation in UI (e2e asserted) · Guided: chips + assistance
- [ ] New track briefs carry a deduped, quality-judged bank; interviewer uses it; creation never blocks
- [ ] Suite + e2e green; pushed
