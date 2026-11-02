# Database Design

## 1. Storage Responsibilities

| Data | Authoritative Store |
|------|---------------------|
| Feedback job lifecycle | PostgreSQL |
| Session lifecycle | PostgreSQL |
| Structured assessment summary | PostgreSQL |
| Guided eligibility and policy audit | PostgreSQL |
| Detailed feedback report and evidence | MongoDB |
| Transcript turns | MongoDB |
| Track memory | MongoDB |
| Question history | MongoDB |
| LLM usage events | MongoDB |

## 2. PostgreSQL Tables

### 2.1 feedback_jobs

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, backend-generated |
| `session_id` | UUID | FK, not null |
| `track_id` | UUID | FK, not null |
| `user_id` | UUID | FK, not null |
| `status` | VARCHAR(30) | not null, enum |
| `attempt_count` | INTEGER | default 0 |
| `max_attempts` | INTEGER | default 5 |
| `correlation_id` | UUID | not null |
| `last_error_code` | VARCHAR(50) | nullable |
| `last_error_at` | TIMESTAMPTZ | nullable |
| `published_at` | TIMESTAMPTZ | nullable |
| `started_at` | TIMESTAMPTZ | nullable |
| `completed_at` | TIMESTAMPTZ | nullable |
| `created_at` | TIMESTAMPTZ | not null, default now() |
| `updated_at` | TIMESTAMPTZ | not null, default now() |

Indexes: `(status, created_at)`, `(session_id)`, `(correlation_id)`, unique `(session_id)` for standard flow.

### 2.2 session_assessment_summaries

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `session_id` | UUID | FK, unique with report_version |
| `user_id` | UUID | FK, not null |
| `track_id` | UUID | FK, not null |
| `mode` | VARCHAR(10) | not null, enum (STRICT/GUIDED) |
| `report_id` | UUID | not null |
| `report_version` | INTEGER | not null |
| `assessment_status` | VARCHAR(20) | not null |
| `coverage_summary` | JSONB | not null |
| `confidence_summary` | JSONB | not null |
| `strict_evidence_summary` | JSONB | nullable |
| `assisted_evidence_summary` | JSONB | nullable |
| `rubric_version` | VARCHAR(50) | not null |
| `created_at` | TIMESTAMPTZ | not null, default now() |

Indexes: `(track_id, created_at DESC)`, `(user_id, created_at DESC)`, unique `(session_id, report_version)`.

### 2.3 track_guided_eligibility

| Column | Type | Constraints |
|--------|------|-------------|
| `track_id` | UUID | PK, FK |
| `status` | VARCHAR(30) | not null, enum |
| `completed_strict_count` | INTEGER | not null, >= 0 |
| `last_evaluated_at` | TIMESTAMPTZ | nullable |
| `policy_version` | VARCHAR(50) | not null |
| `rubric_version` | VARCHAR(50) | not null |
| `evidence_summary` | JSONB | not null |
| `decision_reason_code` | VARCHAR(50) | nullable |
| `decision_explanation` | TEXT | nullable |
| `unlocked_at` | TIMESTAMPTZ | nullable |
| `created_at` | TIMESTAMPTZ | not null, default now() |
| `updated_at` | TIMESTAMPTZ | not null, default now() |

Constraints: `UNLOCKED` requires non-null `unlocked_at`. No transition from `UNLOCKED` to locked.

### 2.4 progression_decision_events

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `track_id` | UUID | FK, not null |
| `user_id` | UUID | FK, not null |
| `previous_status` | VARCHAR(30) | not null |
| `new_status` | VARCHAR(30) | not null |
| `completed_strict_count` | INTEGER | not null |
| `source_session_ids` | UUID[] | not null |
| `policy_version` | VARCHAR(50) | not null |
| `rubric_version` | VARCHAR(50) | not null |
| `evidence_summary_reference` | VARCHAR(255) | not null |
| `reason_code` | VARCHAR(50) | not null |
| `safe_explanation` | TEXT | not null |
| `created_at` | TIMESTAMPTZ | not null, default now() |
| `correlation_id` | UUID | not null |

Index: `(track_id, created_at DESC)`.

## 3. MongoDB Collections

### 3.1 session_feedback_reports

```json
{
  "_id": "report_uuid",
  "user_id": "user_uuid",
  "track_id": "track_uuid",
  "session_id": "session_uuid",
  "job_id": "job_uuid",
  "report_version": 1,
  "session_mode": "STRICT",
  "profile_version_id": "profile_version_uuid",
  "interview_brief_version_id": "brief_version_uuid",
  "summary": {},
  "question_assessments": [],
  "competency_assessments": [],
  "strengths": [],
  "improvement_areas": [],
  "unassessed_topics": [],
  "assistance_summary": {},
  "recommendations": [],
  "limitations": [],
  "source_integrity": {},
  "created_at": "2026-11-02T11:00:00Z",
  "schema_version": 1,
  "graph_version": "1.0.0"
}
```

Indexes: unique `(session_id, report_version)`, `(user_id, created_at DESC)`, `(track_id, created_at DESC)`, `(job_id)`.

### 3.2 session_summaries

Compact per-session summary for quick retrieval.

```json
{
  "_id": "session_uuid",
  "session_id": "session_uuid",
  "track_id": "track_uuid",
  "user_id": "user_uuid",
  "mode": "STRICT",
  "completed_at": "2026-11-02T11:00:00Z",
  "competencies_assessed": 5,
  "competencies_partial": 2,
  "competencies_not_assessed": 3,
  "overall_confidence": "MEDIUM",
  "key_strengths": ["Topic A", "Topic B"],
  "key_gaps": ["Topic C"],
  "report_id": "report_uuid"
}
```

Indexes: `(track_id, completed_at DESC)`, `(user_id, completed_at DESC)`.

### 3.3 track_memories

```json
{
  "_id": "track_uuid",
  "track_id": "track_uuid",
  "user_id": "user_uuid",
  "session_summaries": [
    { "session_id": "session_uuid", "mode": "STRICT", "completed_at": "...", "summary": "..." }
  ],
  "assessed_topics": [
    { "competency_id": "comp_uuid", "last_assessed": "...", "status": "ASSESSED", "confidence": "HIGH" }
  ],
  "not_assessed_topics": [
    { "competency_id": "comp_uuid", "reason": "NOT_COVERED" }
  ],
  "competency_evidence_summary": {},
  "learning_priorities": [
    { "competency_id": "comp_uuid", "priority": "HIGH", "reason": "...", "since": "..." }
  ],
  "question_history": [
    { "question_fingerprint": "hash", "competency_id": "comp_uuid", "asked_in_sessions": ["session_uuid"], "mode": "STRICT" }
  ],
  "recent_assistance_topics": [],
  "current_interview_brief_version": "brief_version_uuid",
  "updated_at": "2026-11-02T11:00:00Z"
}
```

Indexes: `(track_id)`, `(user_id)`.

### 3.4 track_question_history

```json
{
  "_id": "composite_key",
  "track_id": "track_uuid",
  "question_fingerprint": "hash",
  "competency_id": "comp_uuid",
  "first_asked_at": "...",
  "last_asked_at": "...",
  "asked_in_sessions": ["session_uuid"],
  "mode_asked": ["STRICT", "GUIDED"],
  "question_text_normalized": "normalized text"
}
```

Indexes: `(track_id)`, `(question_fingerprint)`, `(competency_id)`.

## 4. Cross-Database Consistency

See `nats_feedback_worker.md` §4 for partial failure recovery scenarios.

Reconciliation process must detect and repair:
- Job complete but report missing in MongoDB.
- Report exists but summary missing in PostgreSQL.
- Summary exists but progression evaluation missing.
- Progression decision exists but session not COMPLETED.
- Session COMPLETED but report reference not found.
- Track memory missing expected session update.