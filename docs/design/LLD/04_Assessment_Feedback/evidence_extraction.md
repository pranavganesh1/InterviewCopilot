# Evidence Extraction and Assessment Model

## 1. Assessment Principles

The Feedback Agent must distinguish:

1. What the interviewer asked.
2. What the candidate answered.
3. What the candidate demonstrated.
4. What cannot be concluded from the available evidence.
5. What assistance was provided before the answer.
6. Which competencies were not adequately assessed.

The system must not equate silence, an omitted question or insufficient interview coverage with demonstrated inability.

Do not make an assessment based only on:
- Resume keywords.
- Candidate claims without interview evidence.
- The model's assumptions about a candidate.
- The expected answer without considering the candidate's actual response.
- A Guided answer that followed a revealing hint as independent unaided mastery.

## 2. Evidence Item Schema

Example:

```json
{
  "evidence_id": "evidence_uuid",
  "session_id": "session_uuid",
  "question_turn_id": "interviewer_turn_uuid",
  "answer_turn_ids": ["candidate_turn_uuid"],
  "competency_id": "competency_uuid",
  "topic": "Database indexing",
  "evidence_type": "CANDIDATE_EXPLANATION",
  "observation": "Candidate explained the purpose of an index and described a trade-off.",
  "evidence_excerpt": "A short exact excerpt from the candidate's response.",
  "assistance_status": "INDEPENDENT",
  "evidence_sufficiency": "SUFFICIENT",
  "confidence": "MEDIUM"
}
```

`evidence_excerpt` should be short and accurate. Prefer turn references plus a concise excerpt rather than copying large transcript sections into the report.

## 3. Question Assessment Schema

```json
{
  "question_assessment_id": "question_assessment_uuid",
  "question_turn_id": "interviewer_turn_uuid",
  "answer_turn_ids": ["candidate_turn_uuid"],
  "competency_id": "competency_uuid",
  "assessment_status": "ASSESSED",
  "observation": "The answer covered the main concept but did not explain the trade-off.",
  "demonstrated_points": [
    "Identified the main purpose"
  ],
  "gaps_observed": [
    "Did not explain the performance trade-off"
  ],
  "evidence_ids": ["evidence_uuid"],
  "assistance_status": "INDEPENDENT",
  "confidence": "MEDIUM",
  "recommendation_refs": ["recommendation_uuid"]
}
```

## 4. Competency Assessment States

Proposed controlled values:

| Status | Meaning |
|--------|---------|
| `ASSESSED` | Sufficient relevant evidence exists for an observation |
| `PARTIALLY_ASSESSED` | Some relevant evidence exists, but coverage is incomplete |
| `NOT_ASSESSED` | The session did not provide enough evidence to assess the competency |
| `INSUFFICIENT_EVIDENCE` | Evidence exists but is too limited, unclear or unreliable for a defensible conclusion |

The team may choose to consolidate `PARTIALLY_ASSESSED` and `INSUFFICIENT_EVIDENCE` after prototype testing. `NOT_ASSESSED` must remain explicit.

## 5. Competency Assessment Example

```json
{
  "competency_id": "competency_uuid",
  "competency_name": "Database indexing",
  "assessment_status": "PARTIALLY_ASSESSED",
  "observation": "The candidate demonstrated a basic understanding but did not explain indexing trade-offs in depth.",
  "evidence_ids": ["evidence_uuid_1", "evidence_uuid_2"],
  "independent_evidence_count": 2,
  "assisted_evidence_count": 0,
  "confidence": "MEDIUM",
  "coverage": {
    "planned": true,
    "questions_asked": 2,
    "questions_answered": 2
  }
}
```

## 6. Confidence and Scoring Policy

The HLD requires confidence/evidence indicators but does not finalize a score scale or calibration. Do not present a numerical threshold as approved.

For the LLD, define confidence categories as descriptive metadata:

- `HIGH`
- `MEDIUM`
- `LOW`

The team must define a consistent rubric for these labels. For example, consider evidence relevance, answer completeness, clarity, question difficulty, coverage and transcript reliability. A confidence label is not a candidate grade.

If numeric competency scores are later used, Member 4 must specify:
- Scale and meaning of each point.
- Domain-specific rubric version.
- How evidence maps to score levels.
- How missing evidence is handled.
- How Guided assistance affects the independent score.
- Calibration and evaluation procedure.
- How score changes across rubric versions are handled.

Do not turn `NOT_ASSESSED` into zero. Do not aggregate a track readiness score from missing competencies as if they were failed.

---

**Open Decision:** Confidence rubric criteria need to be defined (see Open Decisions register). This is a Member 4 responsibility to propose for team review.