# Observability and LLM Usage

## 1. Correlation Propagation

Propagate the following where applicable:
- `user_id`
- `track_id`
- `session_id`
- `job_id`
- `correlation_id`
- `graph_run_id`
- `llm_call_id`
- `report_id`

These identifiers should link FastAPI, NATS, worker, LangGraph, LLM Gateway, MongoDB and PostgreSQL operations.

## 2. Metrics

### 2.1 Job/Worker Metrics

- Feedback jobs queued.
- Queue wait time.
- Processing duration.
- Job success/failure rate.
- Retry count.
- Dead-letter count.
- Duplicate delivery count.
- Time from candidate finish to feedback availability.

### 2.2 Assessment Metrics

- Report validation failure rate.
- Percentage of competencies assessed/partially assessed/not assessed.
- Evidence-reference validation failures.
- Low-confidence assessment rate.
- Strict versus Guided session volume.
- Number of tracks in each eligibility state.

### 2.3 Model Metrics

- LLM calls per feedback job.
- Tokens per feedback job.
- Estimated cost per feedback report.
- Latency by operation and model alias.
- Timeout/error/fallback rates.
- Cost per completed interview-feedback cycle.

Do not log prompt or transcript contents as metric labels.
