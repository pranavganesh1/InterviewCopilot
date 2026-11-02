# Testing Strategy

## 1. Unit Tests

- Question/answer segmentation.
- Turn reference validation.
- Competency mapping.
- Assistance-event classification.
- `NOT_ASSESSED` handling.
- Evidence schema validation.
- Report schema validation.
- Recommendation evidence linking.
- Progression attempt counting.
- Eligibility state transitions.
- Strict/Guided evidence separation.
- Idempotency-key behavior.

## 2. LangGraph Tests

- Valid completed Strict session produces a report.
- Valid completed Guided session produces assisted-evidence metadata.
- Missing transcript stops assessment.
- Incomplete transcript triggers reconciliation/retry path.
- Missing Interview Brief version stops or produces an explicit controlled failure.
- Unmapped question is retained without fabricated competency mapping.
- Insufficient evidence yields `NOT_ASSESSED`/insufficient status.
- Invalid report output follows bounded validation/repair path.
- LLM Gateway timeout follows retry policy.
- Graph does not directly access databases.
- Graph does not set Guided eligibility or session completion.

## 3. Worker/Integration Tests

- Job processed once under normal delivery.
- Duplicate NATS delivery does not duplicate reports.
- Worker crash causes safe redelivery.
- Mongo report persistence failure is recoverable.
- PostgreSQL summary failure is recoverable.
- Memory update is idempotent.
- Progression update is idempotent.
- Completion is not marked before required persistence.
- Dead-letter path works after retry exhaustion.
- Reconciliation detects and repairs supported partial states.

## 4. Progression Policy Test Matrix

| Scenario | Expected Result |
|----------|-----------------|
| New track, zero Strict completions | `LOCKED` |
| One completed Strict session | `LOCKED` |
| Two completed Strict sessions | `LOCKED` |
| Three completed Strict sessions; evidence insufficient | `PENDING_EVIDENCE` |
| Three completed Strict sessions; sufficient evidence, performance not consistently insufficient | `LOCKED_SUFFICIENT` |
| Three completed Strict sessions; sufficient aggregate evidence shows consistent insufficiency | `UNLOCKED` |
| One session is weak but other evidence is satisfactory | Do not unlock based on one session |
| Two Strict sessions plus one Guided session | Strict count is two |
| Three Strict sessions in Track A; Track B has zero | Track A evaluated; Track B remains locked |
| Cancelled/abandoned session | Does not count under current rule |
| Duplicate feedback job for same session | Do not increment count twice |
| Track already unlocked | Remains `UNLOCKED` |

## 5. Security Tests

- User cannot request another user's report.
- Job ID cannot be used as an authorization token.
- Worker cannot load a session not linked to the validated job.
- Agent cannot choose arbitrary user/track/session identifiers to bypass scope.
- Transcript prompt injection does not alter graph instructions or tool allowlist.
- Logs do not contain full prompts, secrets or transcript text by default.

## 6. Acceptance Criteria

Member 4's module is ready for implementation review when:

- The full feedback workflow is documented.
- Feedback is based on the exact session and versioned context.
- Every competency observation is traceable to evidence or explicitly marked insufficient/not assessed.
- Guided assistance is clearly distinguished from independent evidence.
- Detailed report and structured summary have separate, explicit storage ownership.
- Track memory and question-history updates are idempotent.
- Three-Strict-attempt counting is per track and counts completed Strict sessions only.
- Insufficient evidence does not automatically unlock Guided or label the student weak.
- Only backend policy code can persist Guided eligibility.
- NATS duplicate delivery and worker retries cannot duplicate assessments or progression counts.
- Session completion waits for the agreed durable persistence requirements.
