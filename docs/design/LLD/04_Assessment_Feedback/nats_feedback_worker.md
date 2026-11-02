# NATS Feedback Worker

## 1. Worker Behavior

The feedback worker consumes `session.feedback.requested` events from NATS JetStream and processes them asynchronously.

### Processing Rules

- Use a durable JetStream consumer.
- Assume at-least-once delivery.
- Acknowledge only after the message's required durable processing is complete, or use an explicitly designed acknowledgment strategy with safe redelivery.
- Validate `job_id` in PostgreSQL before doing work.
- Validate session status and ownership mapping.
- Process only the referenced `session_id`.
- Use `job_id` and `session_id` as idempotency keys for persistence operations.
- Prevent concurrent duplicate processing for the same job.
- Retry transient provider, storage and network failures with bounded backoff.
- Do not retry permanent validation or authorization failures indefinitely.
- Send exhausted jobs to a dead-letter path and expose a recoverable status.
- Record error codes and correlation IDs; do not log transcript text or prompt contents by default.

### Duplicate Message Behavior

| Job state in PostgreSQL | Worker behavior |
|-------------------------|-----------------|
| `SUCCEEDED` | Acknowledge duplicate; do not regenerate report |
| `PROCESSING` with valid lease/claim | Do not run a second concurrent evaluation |
| `QUEUED` | Claim and process |
| `RETRY_PENDING` | Process according to retry policy |
| `FAILED` / `DEAD_LETTERED` | Follow approved manual/retry policy |
| Unknown job ID | Reject/acknowledge according to security and poison-message policy; record event |

A duplicate delivery must not create duplicate reports, duplicate assessment summaries or increment Strict attempts twice.

## 2. Retry and Backoff Policy

- Initial retry delay: 30 seconds
- Exponential backoff: 2x per retry
- Maximum retry delay: 10 minutes
- Maximum attempts: 5 (configurable)
- Jitter: ±10% to prevent thundering herd

### Retryable Errors
- NATS connection failures
- LLM Gateway timeouts
- Database transient failures (connection pool, deadlock)
- MongoDB transient write failures
- Third-party service timeouts

### Non-Retryable Errors
- Invalid job ID
- Session not found or not owned by user
- Session not in feedback-eligible state
- Transcript incomplete (requires reconciliation, not retry)
- Authorization failures
- Schema validation failures (after bounded repair attempts)

## 3. Dead Letter Handling

After `max_attempts` exhausted:
- Move job to `DEAD_LETTERED` status in PostgreSQL
- Publish to dead-letter subject: `session.feedback.dead_letter`
- Include full error context and correlation IDs
- Alert operations team via configured channel
- Provide manual replay capability with same `job_id`

## 4. Partial Failure Recovery Scenarios

| Failure | Recovery |
|---------|----------|
| NATS publish fails after job creation | Retry publish from durable outbox/job state; do not create another job |
| Worker crashes after receiving event | JetStream redelivers; job claim/lease and idempotency prevent duplicate processing |
| LLM call fails | Bounded retry through LLM Gateway; preserve job state |
| Report generated but Mongo write fails | Retry report persistence using stable report ID |
| Mongo report saved but PostgreSQL summary write fails | Retry summary write; do not regenerate report unnecessarily |
| Summary saved but memory update fails | Retry idempotent memory update |
| Memory update succeeds but progression update fails | Retry progression evaluation from authoritative PostgreSQL state and saved summaries |
| Progression saved but session finalization fails | Retry session finalization; do not increment attempts a second time |
| Worker publishes completion notification but acknowledgment fails | Duplicate notification must be harmless; frontend retrieves current status |

## 5. Idempotency Keys

Use stable identifiers:
- Feedback job: `job_id`
- Report: `(session_id, report_version)` or stable `report_id`
- Structured summary: `(session_id, report_version)`
- Memory update: `(track_id, session_id)`
- Question-history update: `(track_id, session_id)`
- Progression decision: `(track_id, policy_version, source_session_set_hash)` or equivalent deterministic decision key
- Session finalization: `session_id`

## 6. Reconciliation

Provide a scheduled or operator-triggered reconciliation process to identify:
- PostgreSQL feedback job is complete but report is missing in MongoDB.
- MongoDB report exists but PostgreSQL summary is missing.
- Summary exists but progression evaluation is missing.
- Progression decision exists but session remains in a feedback state.
- Session says `COMPLETED` but required report reference cannot be found.
- Track memory does not contain the expected completed session update.

Reconciliation must repair records idempotently or flag the case for manual investigation. It must not invent an assessment result.