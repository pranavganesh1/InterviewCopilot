# Module Overview

## 1. Purpose

This module defines the Low-Level Design for InterviewCopilot's Assessment, Feedback and Progression module.

Member 4 owns the design of:

1. Feedback processing after an interview session.
2. Feedback Agent implemented using LangGraph.
3. Evidence extraction from the exact interview transcript.
4. Competency observations and assessment summaries.
5. Detailed feedback report generation.
6. Explicit `NOT_ASSESSED` outcomes.
7. Track memory and question-history update coordination.
8. Strict Interview attempt aggregation.
9. Backend-enforced Strict/Guided eligibility decisions.
10. NATS feedback worker behavior, retries and recovery.

The purpose of this module is to convert one completed interview into a trustworthy, evidence-linked report and update the candidate's track-specific learning context.

The system must not predict hiring outcomes or judge a candidate's personality or worth. It must describe the evidence observed in the interview, identify evidence limitations, and suggest practical improvements.

## 1.1 Ownership Boundaries

| Area | Owner | Member 4 Responsibility |
|------|-------|-------------------------|
| Authentication and user identity | Member 1 | Consume trusted backend identity context |
| PostgreSQL/MongoDB conventions | Member 1 | Follow shared conventions; propose module schemas |
| NATS infrastructure | Member 1 | Define feedback subject/consumer behavior with Member 1 |
| LLM Gateway and LiteLLM | Member 1 | Use the central gateway only |
| Track and Interview Brief | Member 2 | Consume the exact track and brief version |
| Interview Session and transcript production | Member 3 | Consume completed session and durable turns |
| Feedback Agent graph | Member 4 | Full ownership |
| Detailed assessment and report | Member 4 | Full ownership |
| Track memory/question-history persistence | Shared | Design update contract; coordinate with Member 2/3 and persistence owner |
| Strict/Guided eligibility | Backend domain policy | Design policy evaluation; do not delegate final authority to the LLM |
| Session lifecycle finalization | Session/backend services | Request/coordinate completion after durable writes |

**Important:** Feedback Agent may recommend or return an assessment outcome. A deterministic backend progression-policy service evaluates and persists Guided eligibility. The LLM must not independently unlock Guided mode.

---

## 2. Scope and Fixed Architecture Decisions

### 2.1 In Scope

- Feedback job creation after an interview is finished.
- Durable feedback event delivery through NATS JetStream.
- Worker validation and retrieval of the exact completed session.
- LangGraph Feedback Agent orchestration.
- Transcript-to-question/answer association.
- Evidence extraction and evidence references.
- Competency observations and confidence/evidence sufficiency.
- Strengths, improvement areas and `NOT_ASSESSED` topics.
- Detailed report and structured assessment persistence.
- Track memory and question-history update requests.
- Three-completed-Strict-attempt aggregation per track.
- Guided eligibility decision and audit record.
- Retry, idempotency, dead-letter and reconciliation behavior.

### 2.2 Out of Scope

- Interview question generation and live turn handling (Member 3).
- Track creation and Interview Brief authoring (Member 2).
- Candidate profile editing and authentication (Member 1).
- Final calibrated numerical thresholds for Guided unlock; this remains an open product decision.
- Hiring probability, hiring recommendations or personality scoring.
- Voice-specific assessment implementation; Phase 2 may add audio-derived transcript metadata.
- Code execution or other practical assessment sandboxes.
- Direct database access from the Feedback Agent.

### 2.3 Fixed Architecture Assumptions

| Concern | Selected Direction |
|---------|-------------------|
| Backend | FastAPI modular monolith |
| Agent orchestration | **LangGraph** |
| Model integration | InterviewCopilot LLM Gateway backed by LiteLLM |
| Structured application state | PostgreSQL |
| Detailed transcript/report/memory/history | MongoDB |
| Background jobs | NATS JetStream |
| Files/artifacts | S3-compatible object storage |
| Live text interview | Synchronous FastAPI turns |
| Feedback processing | Asynchronous worker |
| Agent access | Backend-controlled Agent Tool Layer |
| Logical agents | Onboarding, Track Creator, Interviewer and Feedback |

### 2.4 Non-Negotiable Rules

1. PostgreSQL is authoritative for session/job lifecycle, structured assessment summary, track eligibility and progression state.
2. MongoDB stores individual conversation turns, detailed feedback reports, track memory, question history and LLM usage events.
3. The Feedback Agent has no direct database or object-storage credentials.
4. All model calls pass through the InterviewCopilot LLM Gateway and LiteLLM.
5. NATS is at-least-once delivery infrastructure; consumers must be idempotent.
6. A feedback job references one exact session. It must not evaluate a different or newer session.
7. The assessment uses the profile snapshot and Interview Brief version used by that session.
8. A session is not marked `COMPLETED` until the required transcript, detailed report, structured summary, memory/history updates and progression outcome are durably recorded according to the agreed completion contract.
9. A topic that was not adequately assessed is `NOT_ASSESSED`, not a failure.
10. Guided assistance is learning evidence, not independent proof of unaided mastery.
11. Strict attempt counting is per track, not per user globally.
12. The actual performance threshold/calibration remains open; do not invent an approved cutoff.
13. The platform reports observed evidence and preparation opportunities; it does not predict hiring outcomes or judge personal worth.