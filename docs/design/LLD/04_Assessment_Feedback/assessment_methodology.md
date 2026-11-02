# Assessment Methodology

## 1. Strict vs Guided Evidence Handling

### 1.1 Strict Session Evidence

For a Strict session:
- Candidate answer is treated as unaided only if there is no recorded hint or answer assistance before it.
- Natural interviewer follow-up questions are allowed and remain part of the interview context.
- Clarification or repetition of a question should be recorded distinctly from teaching assistance.
- Feedback may assess the candidate's answer against the competency rubric.
- Strict completed sessions can contribute to the three-attempt baseline.

### 1.2 Guided Session Evidence

For a Guided session:
- Record every hint request.
- Record assistance level and type.
- Record the interviewer turn that provided the hint or explanation.
- Link subsequent candidate answers to the preceding assistance event.
- Separate independent evidence from assisted evidence.
- Use assisted observations for coaching and learning recommendations.
- Do not treat an answer produced after a revealing hint/explanation as independent proof of unaided mastery.
- Guided sessions do not count toward the initial three completed Strict attempts.

### 1.3 Assistance Event Schema

```json
{
  "assistance_event_id": "assistance_uuid",
  "session_id": "session_uuid",
  "mode": "GUIDED",
  "requesting_turn_id": "candidate_turn_uuid",
  "assistance_turn_id": "interviewer_turn_uuid",
  "assistance_type": "HINT",
  "assistance_level": 2,
  "topic": "Graph traversal",
  "related_question_turn_id": "question_turn_uuid",
  "created_at": "2026-11-02T10:20:00Z"
}
```

Proposed assistance types (must align with Member 3's turn metadata contract):
- `GENTLE_HINT`
- `SPECIFIC_CLUE`
- `GUIDED_REASONING`
- `FULL_EXPLANATION`
- `EXAMPLE`

### 1.4 Evidence Classification

The assessment pipeline should classify responses as:
- `INDEPENDENT`: no hint or teaching assistance preceded the evaluated response.
- `ASSISTED`: a hint or explanation was supplied before the evaluated response.
- `CLARIFIED`: interviewer repeated or clarified the question without revealing the answer.
- `UNKNOWN`: assistance metadata is missing or the transcript cannot establish the relationship.

`UNKNOWN` must not silently be treated as `INDEPENDENT`.

---

## 2. NOT_ASSESSED Handling

A competency receives `NOT_ASSESSED` when:
- No question in the Interview Brief mapped to that competency was asked.
- The question was asked but the candidate did not answer (or answer was empty).
- The answer contained no relevant evidence for the competency.
- The session was terminated before reaching that competency.

`NOT_ASSESSED` is distinct from failure. It means "we don't have evidence to make an observation." The report must clearly communicate this distinction to the candidate.

---

## 3. Evidence Sufficiency Rules

Evidence is `SUFFICIENT` when:
- The candidate's answer directly addresses the competency.
- The observation is supported by specific, verifiable transcript excerpts.
- The answer demonstrates understanding beyond keyword matching.

Evidence is `INSUFFICIENT` when:
- The answer is vague, incomplete, or contradictory.
- The candidate uses terminology without demonstrating understanding.
- The answer relies on assistance that provided the core concept.

---

## 4. Competency Aggregation Logic

For each competency in the Interview Brief:
1. Collect all question assessments mapped to that competency.
2. Separate `INDEPENDENT` vs `ASSISTED` evidence.
3. If `INDEPENDENT` evidence count >= 1 and at least one is `SUFFICIENT` → `ASSESSED`
4. If `INDEPENDENT` evidence exists but all are `INSUFFICIENT` → `INSUFFICIENT_EVIDENCE`
5. If only `ASSISTED` evidence exists → `PARTIALLY_ASSESSED` (learning observation only)
6. If no evidence exists → `NOT_ASSESSED`

Strict sessions: Only `INDEPENDENT` evidence contributes to assessment status.
Guided sessions: Both `INDEPENDENT` and `ASSISTED` evidence recorded, but only `INDEPENDENT` counts toward Strict baseline.
