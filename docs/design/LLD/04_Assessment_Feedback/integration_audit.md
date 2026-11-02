# Member 4 LLD — Integration Audit Report

**Audit date:** 2026-11-02
**Audited document:** InterviewCopilot_Member4_LLD.md
**Baseline:** InterviewCopilot_4_Member_LLD_Division.md (Sections 8.5, 12, 14)

---

## Executive Summary

Your LLD is **comprehensive and well-structured** — it covers all owned modules (Sections 7.2 A–H in Division doc) and includes most required diagrams, schemas, and design elements. However, it contains **~30 items marked "Proposed", "Suggested", "Illustrative", or "Coordinate with Member X"** that must be resolved against shared contracts before implementation.

**Status:** Design phase — ready for cross-member integration review, not ready for implementation.

---

## 1. Cross-Module Handoff Dependencies (Division §8.5)

| From → To | Handoff Required | Your LLD Status | Action Needed |
|-----------|------------------|-----------------|---------------|
| Member 1 → Member 4 | Identity context, DB conventions, Agent Tool Layer, LLM Gateway, NATS standards | Referenced but not aligned (§5.1, §6.4, §12.5, §14.4) | **BLOCKING** — Wait for Member 1's `common_conventions.md`, `agent_tool_layer.md`, `llm_gateway_litellm.md`, `nats_jetstream.md` |
| Member 2 → Member 4 | Competency definitions, Interview Brief version | Referenced (§8.4, §12.2) | **BLOCKING** — Need Member 2's `interview_brief.md` schema & competency IDs |
| Member 3 → Member 4 | Completed session, transcript, mode, versioned context | Referenced (§4.1, §6.3, §7) | **BLOCKING** — Need Member 3's `session_management.md` terminal states, `turn_management.md` transcript schema, assistance metadata |
| Member 4 → Member 2 | Updated track memory, learning priorities | Designed (§12) but schema not locked | Need Member 2 to confirm `track_memory` contract |
| Member 4 → Member 3 | Updated question history, progression eligibility | Designed (§12, §13) but schema not locked | Need Member 3 to confirm consumption format |

---

## 2. Shared Contracts That Must Be Agreed Before Finalizing (Division §8.1–8.4)

| Contract Area | Your LLD References | Resolution Required |
|---------------|---------------------|---------------------|
| **Common identifiers** (`user_id`, `track_id`, `session_id`, `job_id`, `correlation_id`, `turn_id`, `profile_version_id`, `interview_brief_version_id`, `llm_call_id`) | Used throughout | Adopt Member 1's naming/generation conventions from `common_conventions.md` |
| **Agent invocation envelope** | §6.2, §14.4 | Align with Member 1's `agent_tool_layer.md` |
| **Tool contract template** (name, owning module, allowed agent, input/output schemas, auth, preconditions, side effects, idempotency, errors, audit) | §14.4 lists tools but not full contracts | Complete per Member 1's template in `common_tool_contracts.md` |
| **API response/error envelope** | §14.1–14.3 | Adopt Member 1's `common_api_contracts.md` |
| **NATS subject naming, stream, consumer, ack, retry policy** | §5.1 "Proposed subject", §5.3 "align with Member 1" | Adopt Member 1's `nats_jetstream.md` |
| **MongoDB collection naming, validators, indexes** | §10.4, §12.5 "coordinate with Member 1" | Adopt Member 1's `database_design.md` conventions |
| **PostgreSQL foundational ERD, DDL, shared ownership columns** | §5.2, §11.1, §13.7 | Align with Member 1's `database_design.md` |
| **LangGraph checkpointing & graph version conventions** | §6.3, §7.3 | Adopt Member 1's `langgraph_standards.md` |
| **LLM Gateway call metadata structure** | §17.1 correlation IDs | Align with Member 1's `llm_gateway_litellm.md` |

---

## 3. Items in Your LLD Marked "Proposed / Suggested / Illustrative / Coordinate" 

These must be replaced with **agreed contracts** before implementation:

| Section | Item | Current State | Must Become |
|---------|------|---------------|-------------|
| §5.1 | NATS subject `session.feedback.requested` | "Proposed subject" | Agreed subject from Member 1 |
| §5.2 | `feedback_jobs` table | "Proposed logical table" | Aligned with Member 1's PostgreSQL conventions |
| §5.3 | Job lifecycle statuses | "Align with Member 1's shared job lifecycle conventions" | Shared enum from Member 1 |
| §6.3 | Graph nodes list | "Proposed graph nodes" | Final node set with Member 1's naming conventions |
| §7 | `FeedbackState` TypedDict | "Logical design; exact Python types depend on shared conventions" | Member 1's typed state convention |
| §8.2 | Evidence item schema | "Example" | Formal JSON Schema in `schemas/` |
| §8.3 | Question assessment schema | Example | Formal JSON Schema |
| §8.4 | Competency assessment statuses | "Proposed controlled values" | Agreed enum (consolidate PARTIALLY_ASSESSED/INSUFFICIENT_EVIDENCE?) |
| §8.6 | Confidence rubric | "Define descriptive rubric before numeric score calibration" **OPEN** | Team decision (Member 4 + Product) |
| §9.3 | Assistance types | "Proposed assistance types... align with Member 3's turn metadata contract" | Member 3's enum from `turn_management.md` |
| §10.2 | Report schema | "Example report schema" | Formal JSON Schema in `schemas/` |
| §10.4 | MongoDB `session_feedback_reports` | "Proposed collection" | Aligned with Member 1's MongoDB conventions |
| §11.1 | `session_assessment_summaries` table | "Proposed" | Aligned with Member 1's PostgreSQL conventions |
| §12.5 | MongoDB collections (`session_summaries`, `track_memories`, `track_question_history`) | "Coordinate with Member 1's shared MongoDB conventions" | Member 1's `database_design.md` |
| §13.3 | Eligibility state names | "May be changed to match product's existing enum conventions" | Product decision + Member 1 |
| §13.7 | `track_guided_eligibility` table | "Logical schema proposal" | Aligned with Member 1's PostgreSQL conventions |
| §13.8 | `progression_decision_events` table | Proposal | Aligned with Member 1's PostgreSQL conventions |
| §14.1 | API endpoints | "Coordinate with Member 3 and Member 1" | Member 1's API contract format |
| §14.4 | Tool contracts | "Member 4 should specify these tool schemas with Member 1" | Complete per Member 1's tool contract template |
| §15.3 | Idempotency keys | Defined but not cross-checked | Verify with Member 1's job design |

---

## 4. Division Document Completion Criteria (§7.6) — Status Check

| Criterion | Your LLD Coverage | Gap |
|-----------|-------------------|-----|
| Feedback from exact session + versioned context | ✅ §4.1, §6.4, §7 | Needs Member 3's session context contract |
| Every assessment evidence-linked | ✅ §8, §10 | Schema not finalized |
| `NOT_ASSESSED` supported | ✅ §8.4, §8.5 | Status enum needs team agreement |
| Guided assistance distinguished | ✅ §9 | Needs Member 3's assistance metadata |
| Detailed report + structured summary separate storage | ✅ §10, §11 | Table/collection names need Member 1 alignment |
| Progression per track, backend-enforced | ✅ §13 | Policy thresholds open (§13.6) |
| Three-Strict-attempt logic handles insufficient evidence | ✅ §13.3 `PENDING_EVIDENCE` | ✅ |
| Async retries/duplicate jobs don't duplicate results | ✅ §5.3, §5.5, §15 | Needs Member 1's NATS conventions |
| Session completion waits for durable feedback | ✅ §4.2, §4.3 | ✅ |

---

## 5. Repository Structure (§10) — Your Module

Your LLD §20 proposes:
```
LLD/04_Assessment_Feedback/
├── README.md
├── module_overview.md
├── feedback_workflow.md
├── feedback_agent_langgraph.md
├── evidence_extraction.md
├── assessment_methodology.md
├── feedback_report_schema.md
├── track_memory_updates.md
├── question_history_updates.md
├── progression_policy.md
├── nats_feedback_worker.md
├── database_design.md
├── api_and_tool_contracts.md
├── security_and_privacy.md
├── observability.md
├── testing_strategy.md
├── diagrams/
│   ├── feedback_end_to_end.mmd
│   ├── feedback_agent_graph.mmd
│   ├── feedback_job_state.mmd
│   ├── progression_state.mmd
│   └── cross_database_recovery.mmd
└── schemas/
    ├── feedback_job_event.schema.json
    ├── feedback_report.schema.json
    ├── evidence_item.schema.json
    ├── competency_assessment.schema.json
    └── progression_decision.schema.json
```

**Action:** Create this directory structure and split your monolithic LLD into these files. This is **independent work you can do now** while waiting for shared contracts.

---

## 6. Open Decisions Register (§22) — Your Action Items

| Decision | Status | Owner | Your Next Step |
|----------|--------|-------|----------------|
| Numerical Guided unlock threshold | **OPEN** | Product + Member 4 | Document options for team review (qualitative rule first) |
| Minimum competency coverage for progression | **OPEN** | Member 2 + Member 4 | Sync with Member 2 on Interview Brief competency structure |
| Confidence rubric | **OPEN** | Member 4 | Define descriptive rubric (HIGH/MEDIUM/LOW criteria) |
| Assessment rubric versioning | **RECOMMENDED** | Member 4 | Add `rubric_version` to all report/summary schemas |
| Numeric scores | **OPEN** | Member 4 | Do not finalize; document "not yet calibrated" |
| Re-evaluation after more Strict sessions | **RECOMMENDED** | Member 4 | Your §13.4 allows this — confirm with team |
| Report regeneration | **OPEN** | Member 4 | Define versioning policy (explicit regeneration only) |
| Memory update as completion prerequisite | **CONFIRM WITH TEAM** | All | Your §4.3 notes HLD order — team decision needed |
| NATS outbox implementation | **CONFIRM WITH MEMBER 1** | Member 1 | Wait for Member 1's `nats_jetstream.md` |
| LangGraph checkpoint store | **CONFIRM WITH MEMBER 1** | Member 1 | Wait for Member 1's `langgraph_standards.md` |
| Feedback model selection | **OPEN** | Member 1 | Wait for Member 1's `llm_gateway_litellm.md` |
| Report retention/deletion | **OPEN** | Member 1 | Wait for Member 1's privacy policy |

---

## 7. What You Can Do NOW (Independent of Other Members)

### A. Split LLD into repository structure (§10)
Create `LLD/04_Assessment_Feedback/` with the 15+ markdown files and 5 schema files. This forces you to formalize each section.

### B. Write formal JSON Schemas for all "Example" / "Proposed" schemas
- `schemas/feedback_job_event.schema.json`
- `schemas/feedback_report.schema.json`
- `schemas/evidence_item.schema.json`
- `schemas/competency_assessment.schema.json`
- `schemas/progression_decision.schema.json`

### C. Define the **Confidence Rubric** (Open Decision)
Document concrete criteria for HIGH/MEDIUM/LOW based on:
- Evidence relevance
- Answer completeness
- Clarity
- Question difficulty
- Coverage
- Transcript reliability

### D. Define **Assessment Rubric Versioning**
Add `rubric_version` field to every report, summary, eligibility record. Specify how version changes affect historical comparisons.

### E. Formalize **Report Regeneration Policy**
- When is a new `report_version` created?
- What triggers regeneration?
- How are previous versions archived?

### F. Write **Unit Tests** for core logic (no integration needed)
- Evidence extraction from transcript segments
- Competency aggregation logic
- `NOT_ASSESSED` handling
- Progression policy state machine (§13.4)
- Idempotency key generation
- Strict vs Guided evidence classification

### G. Create **Mermaid Diagrams** in `diagrams/`
Convert inline diagrams to separate `.mmd` files:
- `feedback_end_to_end.mmd` (from §4.1)
- `feedback_agent_graph.mmd` (from §6.4)
- `feedback_job_state.mmd` (from §5.3)
- `progression_state.mmd` (from §13.4)
- `cross_database_recovery.mmd` (from §15.2)

### H. Document **Security Test Cases** (§18.5)
Formalize as executable test specs.

---

## 8. Questions to Send Other Members (When They're Ready)

### To Member 1 (Platform)
1. What are the final common identifier naming conventions? (`user_id` vs `userId` vs `user_uuid`)
2. What is the Agent Tool Layer contract template? (input/output schemas, auth, idempotency, errors)
3. What are the NATS stream/subject naming conventions? Consumer ack policy? Retry/backoff?
4. What are the MongoDB collection naming conventions, common envelope fields, index patterns?
5. What are the PostgreSQL foundational conventions (audit columns, FK patterns, UUID vs ULID)?
6. What is the common API response/error envelope?
7. What is the LangGraph state convention and checkpointing approach?
8. What is the LLM Gateway call metadata structure?
9. What is the job lifecycle status enum shared across all job types?

### To Member 2 (Track Management)
1. What is the final Interview Brief JSON Schema? (versioned, with competency IDs)
2. What are the competency IDs and definitions? (stable identifiers for mapping)
3. What is the track memory document structure? (so we can update it correctly)
4. What is the learning priority update format?
5. How does track refresh affect historical assessment context?

### To Member 3 (Interview Engine)
1. What are the exact session terminal states? (COMPLETING, FEEDBACK_PENDING, FEEDBACK_PROCESSING, COMPLETED, FAILED...)
2. What is the transcript turn schema? (turn_id, sequence, role, content, metadata)
3. What is the assistance event metadata schema? (types, levels, linkage to question/answer)
4. How are questions linked to answers in the transcript?
5. What is the finish-interview → feedback-job handoff contract? (what Member 3 publishes, what Member 4 consumes)
6. What is the exact definition of a "completed Strict attempt" for progression counting?

---

## 9. Recommended Next Steps (Priority Order)

| Priority | Action | Depends On |
|----------|--------|------------|
| **P0** | Create `LLD/04_Assessment_Feedback/` directory structure and split LLD | None — do now |
| **P0** | Write 5 JSON Schema files in `schemas/` | None — do now |
| **P0** | Define Confidence Rubric (HIGH/MEDIUM/LOW criteria) | None — do now |
| **P0** | Define Assessment Rubric Versioning strategy | None — do now |
| **P0** | Define Report Regeneration policy | None — do now |
| **P0** | Write unit tests for core logic (evidence extraction, progression policy, idempotency) | None — do now |
| **P1** | Convert inline Mermaid diagrams to `diagrams/*.mmd` files | P0 |
| **P1** | Formalize security test cases as executable specs | P0 |
| **P2** | Send integration questions to Member 1, 2, 3 (use template above) | Their LLDs published |
| **P3** | Align all "Proposed" items with shared contracts | Member 1/2/3 contracts finalized |
| **P3** | Finalize API endpoints with Member 1's contract format | Member 1 |
| **P3** | Finalize tool contracts with Member 1's template | Member 1 |
| **P3** | Finalize NATS/MongoDB/PostgreSQL schemas with Member 1 | Member 1 |
| **P3** | Finalize session/transcript/assistance contracts with Member 3 | Member 3 |
| **P3** | Finalize Interview Brief/competency/memory contracts with Member 2 | Member 2 |

---

## 10. What NOT to Do Yet

- ❌ Do **not** write FastAPI route handlers for feedback APIs
- ❌ Do **not** write NATS consumer/worker implementation
- ❌ Do **not** write LangGraph graph compilation code
- ❌ Do **not** write MongoDB/PostgreSQL repository classes
- ❌ Do **not** write Agent Tool Layer tool implementations
- ❌ Do **not** write LLM Gateway client code
- ❌ Do **not** write integration tests with other modules

**Wait for:** Member 1's shared contracts, Member 2's Interview Brief schema, Member 3's session/transcript contracts.

---

## Summary

Your LLD is **design-complete for internal module logic** but **integration-incomplete** for cross-module contracts. 

**Immediate productive work:** Split the document, write JSON schemas, define the confidence rubric, write unit tests for pure logic, create diagram files. These are all **blocker-free** and will accelerate implementation once contracts land.

**Blocked work:** Any code touching NATS, databases, Agent Tool Layer, LLM Gateway, API endpoints, or other modules' data structures.

---

*Generated from audit of InterviewCopilot_Member4_LLD.md against InterviewCopilot_4_Member_LLD_Division.md*