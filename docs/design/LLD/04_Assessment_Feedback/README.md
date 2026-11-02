# Assessment, Feedback & Progression — Member 4 LLD

**Module owner:** Member 4
**Architecture baseline:** InterviewCopilot HLD v0.2 (2026-10-31)
**Orchestration:** LangGraph
**Backend:** FastAPI modular monolith
**Primary workflow:** Asynchronous feedback processing after text interview

---

## Document Index

| File | Purpose |
|------|---------|
| `module_overview.md` | Purpose, scope, ownership boundaries, non-negotiable rules |
| `feedback_workflow.md` | End-to-end async workflow, session completion definition, NATS job design |
| `feedback_agent_langgraph.md` | Feedback Agent graph design, nodes, state schema, conditional routing |
| `evidence_extraction.md` | Evidence extraction, assessment model, Strict vs Guided evidence handling |
| `assessment_methodology.md` | Assessment principles, competency states, confidence/scoring policy |
| `feedback_report_schema.md` | Detailed report sections, schemas, MongoDB document design |
| `track_memory_updates.md` | Track memory/question-history update design, merge rules, MongoDB collections |
| `progression_policy.md` | Strict/Guided eligibility, state machine, evaluation algorithm, audit |
| `nats_feedback_worker.md` | Worker behavior, retry, idempotency, dead-letter, reconciliation |
| `database_design.md` | PostgreSQL tables, MongoDB collections, cross-db consistency |
| `api_and_tool_contracts.md` | Public APIs, internal tool contracts, Agent Tool Layer schemas |
| `security_and_privacy.md` | Authorization, prompt injection, privacy, assessment boundaries |
| `observability.md` | Correlation IDs, metrics, LLM usage tracking |
| `testing_strategy.md` | Unit, graph, worker/integration, progression policy, security tests |
| `diagrams/` | Mermaid diagrams (5 files) |
| `schemas/` | JSON Schemas (5 files) |

---

## Integration Status

See [`integration_audit.md`](integration_audit.md) for cross-module dependency audit against Division document.

**Key blocking dependencies:**
- Member 1: Common conventions, Agent Tool Layer, LLM Gateway, NATS standards, DB conventions
- Member 2: Interview Brief schema, competency IDs, track memory structure
- Member 3: Session terminal states, transcript schema, assistance metadata, finish→feedback handoff

---

## Implementation Sequence (from LLD §19)

| Step | Work | Depends On |
|------|------|------------|
| 1 | Agree session/transcript/report contracts with Members 1–3 | Member 1/2/3 contracts |
| 2 | Define feedback job and event schema | Member 1 NATS conventions |
| 3 | Implement job validator and worker skeleton | Member 1 NATS conventions |
| 4 | Implement exact-session context loader | Member 3 session contract |
| 5 | Define Feedback LangGraph state and nodes | Member 1 LangGraph standards |
| 6 | Implement segmentation and evidence extraction | — |
| 7 | Implement competency aggregation and coverage | Member 2 competency IDs |
| 8 | Implement report generation and validation | — |
| 9 | Implement Mongo/PostgreSQL persistence | Member 1 DB conventions |
| 10 | Implement memory/question-history update contract | Member 2 memory structure |
| 11 | Implement deterministic progression policy | — |
| 12 | Implement retry, idempotency, reconciliation | Member 1 NATS conventions |
| 13 | Add metrics, audit events, tests | — |
| 14 | End-to-end tests with Member 3 | Member 3 session completion |

---

## Open Decisions (from LLD §22)

| Decision | Status | Owner |
|----------|--------|-------|
| Numerical Guided unlock threshold | OPEN | Product + Member 4 |
| Minimum competency coverage for progression | OPEN | Member 2 + Member 4 |
| Confidence rubric (HIGH/MEDIUM/LOW criteria) | OPEN | Member 4 |
| Assessment rubric versioning | RECOMMENDED | Member 4 |
| Numeric scores | OPEN | Member 4 |
| Re-evaluation after more Strict sessions | RECOMMENDED | Member 4 |
| Report regeneration policy | OPEN | Member 4 |
| Memory update as completion prerequisite | CONFIRM WITH TEAM | All |
| NATS outbox implementation | CONFIRM WITH MEMBER 1 | Member 1 |
| LangGraph checkpoint store | CONFIRM WITH MEMBER 1 | Member 1 |
| Feedback model selection | OPEN | Member 1 |
| Report retention/deletion | OPEN | Member 1 |

---

## Quick Links

- [Master LLD Division Document](../../InterviewCopilot_4_Member_LLD_Division.md)
- [Member 4 Full LLD (monolithic)](../../InterviewCopilot_Member4_LLD.md)
- [Integration Audit](integration_audit.md)
