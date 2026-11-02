# Feedback Report Schema

## 1. Report Sections

The detailed report must contain:

1. Session overview.
2. Mode and session context.
3. Interview coverage.
4. Question-by-question observations.
5. Competency-level observations.
6. Demonstrated strengths.
7. Improvement areas.
8. Unassessed topics.
9. Evidence references.
10. Confidence/evidence limitations.
11. Guided assistance usage, if applicable.
12. Practical recommendations.
13. Suggested next preparation priorities.

The report must not make a hiring prediction, state that a company will or will not hire the candidate, or judge the candidate's personality or worth.

## 2. Report Schema (JSON)

```json
{
  "report_id": "report_uuid",
  "report_version": 1,
  "user_id": "user_uuid",
  "track_id": "track_uuid",
  "session_id": "session_uuid",
  "session_mode": "STRICT",
  "profile_version_id": "profile_version_uuid",
  "interview_brief_version_id": "brief_version_uuid",
  "generated_at": "2026-11-02T11:00:00Z",
  "summary": {
    "overview": "The candidate demonstrated a basic understanding of the covered topics.",
    "coverage_status": "PARTIAL",
    "confidence": "MEDIUM"
  },
  "question_assessments": [],
  "competency_assessments": [],
  "strengths": [],
  "improvement_areas": [],
  "unassessed_topics": [],
  "assistance_summary": {
    "assistance_used": false,
    "events": []
  },
  "recommendations": [],
  "limitations": [],
  "source_integrity": {
    "transcript_complete": true,
    "source_turn_count": 12
  }
}
```

## 3. Recommendation Schema

```json
{
  "recommendation_id": "recommendation_uuid",
  "competency_id": "competency_uuid",
  "topic": "Database indexing",
  "priority": "HIGH",
  "reason": "The candidate identified the purpose of an index but did not explain trade-offs.",
  "suggested_action": "Review index selectivity and write-amplification trade-offs, then practice explaining them.",
  "supporting_evidence_ids": ["evidence_uuid"],
  "suggested_practice_type": "CONCEPT_REVIEW_AND_MOCK_QUESTION"
}
```

Priority values and recommendation categories should be standardized across domain packs. If no reliable evidence supports a recommendation, omit it rather than inventing a weakness.

## 4. MongoDB Document Design

Proposed collection: `session_feedback_reports`.

One report document per session/report generation version.

Recommended fields:
- `_id` / `report_id`
- `user_id`
- `track_id`
- `session_id`
- `job_id`
- `report_version`
- `session_mode`
- `profile_version_id`
- `interview_brief_version_id`
- `summary`
- `question_assessments`
- `competency_assessments`
- `strengths`
- `improvement_areas`
- `unassessed_topics`
- `assistance_summary`
- `recommendations`
- `limitations`
- `source_integrity`
- `created_at`
- `schema_version`
- `graph_version`

Recommended indexes:
- Unique `(session_id, report_version)`.
- `(user_id, created_at DESC)`.
- `(track_id, created_at DESC)`.
- `(job_id)`.

Avoid placing an unbounded transcript inside the report. Store turn references and concise evidence excerpts.
