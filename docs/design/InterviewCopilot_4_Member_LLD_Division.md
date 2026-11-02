# InterviewCopilot --- Final Four-Member LLD Work Division

**Document type:** Low-Level Design (LLD) work-allocation plan\
**Architecture baseline:** InterviewCopilot High-Level Design (HLD),
v0.2\
**Selected agent orchestration framework:** LangGraph\
**Backend style:** FastAPI modular monolith\
**Team structure:** Four members, with shared integration standards

------------------------------------------------------------------------

## 1. Purpose

This document divides the InterviewCopilot Low-Level Design work among
four team members. Each member owns a clearly defined set of modules and
must produce implementation-ready design specifications for those
modules.

The division follows functional ownership:

1.  **Member 1 --- Platform, Data Foundation & Onboarding**
2.  **Member 2 --- Track Management & Track Creator Agent**
3.  **Member 3 --- Interview Engine & Interviewer Agent**
4.  **Member 4 --- Assessment, Feedback & Progression**

The four logical agents remain:

-   Onboarding Agent
-   Track Creator Agent
-   Interviewer Agent
-   Feedback Agent

The developer division does not create additional agents. Member 1 owns
the Onboarding Agent and the shared platform foundation.

The objective is to produce one integrated LLD, not four disconnected
designs.

------------------------------------------------------------------------

## 2. Architecture decisions to treat as fixed

Unless the team formally revises the HLD, all four members must design
against the following decisions.

  -----------------------------------------------------------------------
  Area                                Selected design
  ----------------------------------- -----------------------------------
  Frontend                            Web-first application

  Backend                             FastAPI modular monolith

  Agent orchestration                 **LangGraph**

  LLM integration                     LangChain components where useful

  LLM gateway                         InterviewCopilot-owned gateway
                                      built around LiteLLM Proxy

  Primary application database        PostgreSQL

  Conversation, memory and detailed   MongoDB
  report storage

  Asynchronous jobs and events        NATS JetStream

  File storage                        S3-compatible object storage

  Phase 1 interview interface         Text

  Phase 2 interview interface         Server-side streaming voice

  Agent count                         Four logical agents

  Agent-to-data access                Through backend-controlled tools
                                      only
  -----------------------------------------------------------------------

### 2.1 Non-negotiable architecture rules

1.  PostgreSQL is the authoritative source of truth for application
    state, ownership, lifecycle and progression eligibility.
2.  MongoDB stores detailed conversation turns, session summaries, track
    memories, question history, detailed feedback reports and LLM usage
    events.
3.  Original uploaded files are stored in object storage. The database
    stores file metadata and storage keys.
4.  Agents must not connect directly to PostgreSQL, MongoDB, object
    storage, external model providers or another user's data.
5.  Agents request operations through the backend-controlled Agent Tool
    Layer.
6.  All model calls must pass through the InterviewCopilot LLM Gateway
    and LiteLLM Proxy.
7.  LangGraph orchestrates agent workflows. It is not the source of
    truth for business state.
8.  Backend services enforce authorization, ownership, lifecycle
    transitions, session completion and Strict/Guided eligibility.
9.  NATS JetStream is for asynchronous work. Phase 1 live interview
    turns use synchronous FastAPI request/response handling; do not put
    every live turn on NATS.
10. Start with a modular monolith. Do not split each agent into a
    microservice for Phase 1.
11. Do not add Redis or a separate vector database in Phase 1 unless a
    demonstrated requirement justifies it.
12. Every track has independent sessions, memory, question history,
    assessment evidence and Strict/Guided eligibility.
13. A session retains the candidate profile version and Interview Brief
    version used when it was conducted.
14. A session is not marked complete until its transcript and feedback
    have been durably persisted.
15. Guided assistance is coaching and must not be counted as independent
    evidence of unaided mastery.

------------------------------------------------------------------------

## 3. Team ownership at a glance

  -----------------------------------------------------------------------
  Member            Primary ownership Logical agent     Main output
                                      ownership
  ----------------- ----------------- ----------------- -----------------
  Member 1          Platform, data,   Onboarding Agent  Foundation LLD
                    shared LangGraph                    and shared
                    integration,                        technical
                    authentication,                     standards
                    profile,
                    documents and
                    infrastructure

  Member 2          Track lifecycle,  Track Creator     Track Management
                    preparation,      Agent             and Track Creator
                    research and                        LLD
                    Interview Brief

  Member 3          Session           Interviewer Agent Interview Engine
                    lifecycle,                          LLD
                    interview turns,
                    Strict/Guided
                    runtime and
                    adaptive
                    interviewing

  Member 4          Transcript        Feedback Agent    Assessment and
                    assessment,                         Feedback LLD
                    feedback reports,
                    memory updates
                    and progression
                    policy
  -----------------------------------------------------------------------

### Ownership boundary

Each member is responsible for designing their module in detail, but
shared contracts must be agreed upon before implementation. A member
must not independently redefine common identity fields, session states,
error formats, event envelopes or agent invocation conventions.

------------------------------------------------------------------------

# 4. Member 1 --- Platform, Data Foundation & Onboarding

## 4.1 Objective

Design the platform foundation used by every other module. Establish the
common backend, data, security, agent integration and LLM access
patterns. Also design the Onboarding Agent.

This member has an enabling responsibility: the other members depend on
the interfaces and conventions produced here.

## 4.2 Modules owned

### A. Authentication and application identity

Design:

-   Google and Apple OIDC sign-in flow.
-   OIDC callback handling and identity validation.
-   Application session creation and expiration.
-   Session refresh and logout behavior.
-   Mapping from external identity to internal user ID.
-   Authentication middleware/dependencies in FastAPI.
-   User identity propagation into backend services and agent tool
    calls.
-   Unauthorized, expired-session and invalid-token behavior.

Specify the exact trust boundary: the backend derives the authenticated
user ID. A client or agent must not be allowed to choose an arbitrary
user ID for an operation.

### B. Candidate Profile

Design:

-   Candidate profile creation, retrieval and update.
-   Academic background and education records.
-   Skills and proficiency information.
-   Projects, internships and work experience.
-   Certifications and other candidate context.
-   Profile completion status.
-   Profile versioning and snapshot behavior.
-   Validation rules for profile fields.
-   Ownership and access rules.

The design must distinguish the current editable profile from the
immutable profile snapshot associated with a completed or active
interview session.

### C. Document Management

Design:

-   Resume and supporting document upload.
-   File type and size validation.
-   Secure object-storage key generation.
-   Upload metadata and ownership.
-   Document processing job creation.
-   Processing status and error states.
-   Retry and failure behavior.
-   Extracted text and structured extraction result references.
-   Document deletion and retention behavior, where applicable.

Original files belong in object storage. PostgreSQL stores metadata and
references; do not store file binaries in PostgreSQL or MongoDB.

### D. Shared database foundation

Own the cross-system database conventions and the foundational schemas.

**PostgreSQL design responsibilities:**

-   Users and external authentication identities.
-   Application sessions.
-   Candidate profiles and profile versions.
-   Document metadata and processing status.
-   Common audit fields and ownership conventions.
-   Shared identifiers and foreign-key conventions.
-   Indexing, uniqueness and transaction boundaries.

**MongoDB design responsibilities:**

-   Shared collection naming conventions.
-   Common document envelope fields.
-   `user_id`, `track_id`, `session_id` and sequence identifiers where
    applicable.
-   Indexing conventions and retention considerations.
-   Avoiding unbounded arrays in documents; conversation turns should be
    separate documents rather than one ever-growing array.

Do not take over the detailed Track, Interview Session or Feedback
domain schemas from other members. Define shared conventions and review
their proposed schemas for consistency.

### E. NATS JetStream and background processing foundation

Design:

-   Stream and subject naming conventions.
-   Job/event envelope.
-   Opaque backend-created `job_id` and correlation ID.
-   PostgreSQL mapping from job ID to authorized operation and entity.
-   Consumer behavior and acknowledgment.
-   At-least-once delivery assumptions.
-   Idempotent job handling.
-   Retry and backoff policy.
-   Dead-letter handling.
-   Reconciliation for jobs that fail between database persistence and
    message publication.

Initial job categories include:

-   Document processing.
-   Profile enrichment.
-   Track preparation.
-   Company research.
-   Session feedback.
-   Track memory update.

Do not route every live interview turn through NATS.

### F. LLM Gateway and LiteLLM

Design the shared model-access path:

-   InterviewCopilot LLM Gateway interface.
-   LiteLLM Proxy integration.
-   Service/agent authentication.
-   Model aliases and provider routing.
-   Operation-based model allowlists.
-   Timeouts, retries and fallback behavior.
-   Request and response validation.
-   Token, latency, error and estimated-cost capture.
-   Correlation identifiers.
-   Privacy-aware logging and redaction.
-   Handling unavailable token/cost fields.

Define a common model-call metadata structure containing, where
available:

-   `llm_call_id`
-   `user_id`
-   `track_id`
-   `session_id`
-   `agent_name`
-   `operation`
-   `provider`
-   `model_alias`
-   `actual_model`
-   input, output, cached, reasoning and total token counts
-   latency
-   estimated cost and pricing version
-   status
-   correlation ID

Detailed usage events are stored in MongoDB. Do not store full prompts
and responses in analytics by default.

### G. Agent Tool Layer and LangGraph foundation

This is a key responsibility for Member 1.

Design the common mechanism through which LangGraph nodes request
backend operations.

Specify:

-   How FastAPI invokes a graph.
-   How authenticated identity and request context are passed to a
    graph.
-   How graph nodes access approved tools.
-   Role-specific tool allowlists.
-   Tool argument and output schemas.
-   Ownership and scope checks.
-   State-transition validation.
-   Idempotency and audit requirements.
-   Tool error representation.
-   How agents are prevented from accessing databases or providers
    directly.

Define common LangGraph conventions:

-   Graph construction and compilation conventions.
-   Typed state conventions.
-   Node naming and responsibility conventions.
-   Conditional-edge conventions.
-   Graph input/output contracts.
-   Checkpointing requirements and approved persistence approach.
-   Correlation and tracing propagation.
-   Retry and error boundaries.
-   Versioning of graph definitions.

**Important:** Do not make LangGraph checkpoints the authoritative
application record. PostgreSQL and MongoDB retain their assigned
source-of-truth responsibilities. The team must specify how checkpoint
data is stored and governed without bypassing the HLD's data ownership
rules.

### H. Onboarding Agent

Design the Onboarding Agent graph for optional conversational profile
enrichment.

Potential tools, consistent with the HLD:

-   `get_candidate_profile`
-   `save_basic_profile_info`
-   `add_academic_context`
-   `add_skill`
-   `add_project`
-   `add_internship`
-   `add_experience`
-   `request_document_processing`
-   `get_profile_completion_status`

For each tool, document input schema, output schema, authorization
checks, validation, persistence effect and failure behavior.

## 4.3 Required diagrams

1.  OIDC authentication sequence diagram.
2.  Document upload and processing sequence diagram.
3.  Candidate profile update sequence diagram.
4.  Onboarding Agent LangGraph diagram.
5.  Agent Tool Layer component diagram.
6.  LLM Gateway request sequence diagram.
7.  NATS job lifecycle diagram.
8.  Shared data-store architecture diagram.

## 4.4 Required API and schema deliverables

-   Authentication API specifications.
-   Candidate Profile API specifications.
-   Document Management API specifications.
-   Shared error response format.
-   Shared identity/request context schema.
-   Common agent invocation request/response schema.
-   Common tool-call contract.
-   Common event/job envelope.
-   PostgreSQL foundational ERD and DDL proposal.
-   MongoDB collection conventions and index proposal.
-   LLM usage event schema.

## 4.5 Member 1 completion criteria

-   All other members can use the same identity and tool conventions.
-   Database ownership and shared identifiers are documented.
-   Model calls have one approved gateway path.
-   Agent tools cannot bypass backend authorization.
-   Onboarding Agent has a complete graph and tool specification.
-   Async job behavior is documented, including duplicate delivery and
    retry cases.

------------------------------------------------------------------------

# 5. Member 2 --- Track Management & Track Creator Agent

## 5.1 Objective

Design how candidates create, configure, prepare and maintain
independent Preparation Tracks. Design the Track Creator Agent using
LangGraph.

A track may be topic-based, role-based or company/job-description-based.

## 5.2 Modules owned

### A. Track Management

Design:

-   Track creation.
-   Track listing and retrieval.
-   Track update and archive behavior.
-   Track type: topic, role or company/JD.
-   Track ownership and isolation.
-   Track lifecycle and readiness states.
-   Track configuration and target competencies.
-   Track refresh and versioning.
-   Rules for creating a new track versus refreshing an existing one.

Define how each track maintains independent:

-   Interview sessions.
-   Interview Brief.
-   Track memory.
-   Question history.
-   Assessment evidence.
-   Learning priorities.
-   Strict/Guided eligibility.

### B. Track Creator Agent

Design the Track Creator Agent as a LangGraph workflow.

The graph should cover, as applicable:

1.  Receive track creation or refresh request.
2.  Validate the request and track type.
3.  Retrieve candidate context through approved tools.
4.  Retrieve and interpret the job description, if supplied.
5.  Gather company/role/topic research when relevant.
6.  Identify competencies and coverage areas.
7.  Build a preparation plan.
8.  Generate the Interview Brief.
9.  Validate required output structure.
10. Save versioned artifacts through backend tools.
11. Mark the track ready through the backend.

The graph must be explicit about which steps are conditional for
topic-based, role-based and company/JD-based tracks.

### C. Interview Brief

Design the Interview Brief structure and versioning.

Specify fields for, as appropriate:

-   Track ID and version.
-   Track type and target.
-   Role/company/JD context.
-   Competency list.
-   Competency descriptions.
-   Topic and subtopic coverage.
-   Question categories.
-   Difficulty distribution.
-   Interview objectives.
-   Expected coverage or constraints.
-   Research references and source metadata.
-   Creation timestamp and status.

The exact final schema is an LLD decision. Keep it versioned and ensure
the Interviewer and Feedback Agents can consume the correct version.

### D. Preparation Plan

Design:

-   Topic-wise preparation structure.
-   Competency-to-topic mapping.
-   Recommended learning priorities.
-   Preparation status.
-   Links between preparation priorities and later feedback.
-   How refreshed briefs affect existing tracks and sessions.

Avoid claiming that a candidate has mastered a topic merely because the
Track Creator generated a preparation plan.

### E. Company and JD research

Design:

-   JD ingestion and storage references.
-   Company research workflow.
-   Source capture and reference metadata.
-   Handling missing or conflicting source information.
-   Research freshness and refresh conditions.
-   Untrusted external content handling.

Treat resumes, JDs and web content as data, not as instructions to the
agent.

### F. Track context and memory initialization

Design how a new track receives its initial context and how an existing
track reuses its valid context.

Specify:

-   Candidate context snapshot/reference.
-   Track-specific memory initialization.
-   Initial question-history state.
-   Brief version association.
-   Track refresh conditions.
-   Context package provided to the Interviewer Agent.

The Track Creator should not run on every interview start. It should run
for a new track or a material refresh.

## 5.3 LangGraph design requirements

Document:

-   Typed graph state.
-   Nodes and their individual responsibilities.
-   Normal and conditional edges.
-   Tool calls and tool contracts.
-   Graph input/output schema.
-   Validation and retry paths.
-   Failure and partial-completion behavior.
-   Checkpointing and resume behavior.
-   Graph versioning.
-   How backend services persist the resulting track and brief.

The graph must request backend operations through the Agent Tool Layer.
It must not write directly to PostgreSQL or MongoDB.

## 5.4 Required diagrams

1.  Track creation sequence diagram.
2.  Track refresh sequence diagram.
3.  Track lifecycle/state diagram.
4.  Track Creator LangGraph workflow.
5.  Interview Brief generation and persistence sequence diagram.
6.  Track isolation/context-loading diagram.
7.  Company/JD research workflow.

## 5.5 Required API and schema deliverables

-   Track CRUD API specifications.
-   Track creation/refresh request and response schemas.
-   Track database schema proposal.
-   Interview Brief JSON schema.
-   Preparation Plan schema.
-   Research source schema.
-   Track readiness and lifecycle state definitions.
-   Track Creator tool contracts.
-   Track context package contract for the Interviewer Agent.

## 5.6 Member 2 completion criteria

-   Topic, role and company/JD tracks are represented.
-   Each track is isolated from other tracks.
-   The Track Creator graph has explicit nodes and conditional paths.
-   Interview Brief is versioned and consumable by other agents.
-   Track refresh behavior is clear.
-   The design does not regenerate the track on every interview start.

------------------------------------------------------------------------

# 6. Member 3 --- Interview Engine & Interviewer Agent

## 6.1 Objective

Design the runtime interview experience, including session lifecycle,
turn-by-turn interaction, adaptive questioning and Strict/Guided
behavior. Design the Interviewer Agent using LangGraph.

Phase 1 is text-first. Voice is a Phase 2 extension.

## 6.2 Modules owned

### A. Interview Session Management

Design:

-   Session creation.
-   Session initialization.
-   Active session retrieval.
-   Pause and resume.
-   Session completion request.
-   Session cancellation/abandonment behavior, if supported.
-   Session ownership and track association.
-   Session mode and mode snapshot.
-   Candidate profile snapshot reference.
-   Interview Brief version reference.
-   Session status and timestamps.
-   Duplicate request and retry handling.

Use the HLD lifecycle as the baseline:

`CREATED → INITIALIZING → ACTIVE`

`ACTIVE ↔ PAUSED`

`ACTIVE → COMPLETING → FEEDBACK_PENDING → FEEDBACK_PROCESSING → COMPLETED`

Failure/retry states must also be specified. Do not invent incompatible
lifecycle states without documenting the change.

### B. Interviewer Agent

Design the Interviewer Agent as a LangGraph workflow.

It should support:

-   Initial question selection.
-   Candidate answer handling.
-   Follow-up question decisions.
-   Adaptive questioning.
-   Competency coverage.
-   Difficulty adjustment where appropriate.
-   Interview time/turn constraints.
-   Question-history awareness.
-   Strict and Guided mode behavior.
-   Session context loading.
-   Appropriate interview closure.

The graph should balance a planned interview structure with adaptive
follow-ups. It must not lose required competency coverage simply because
the conversation takes an unexpected direction.

### C. Strict Mode

Specify:

-   No coaching or answer-revealing assistance.
-   Independent candidate response collection.
-   Follow-up behavior.
-   Question selection and coverage.
-   What evidence is recorded.
-   How the session is marked as Strict.
-   How Strict sessions contribute to the progression baseline.

New tracks start with Strict Interviews.

### D. Guided Mode

Specify:

-   Backend verification of Guided eligibility before the mode is used.
-   Progressive hints.
-   Concept explanations.
-   Examples where appropriate.
-   How the candidate can request help.
-   How assistance is represented in the transcript and assessment
    metadata.
-   How the agent returns to normal interviewing after assistance.
-   How assisted responses are distinguished from independent responses.

Guided mode is a normal interview with optional coaching, not a separate
exam. Guided assistance must not count as independent evidence of
unaided mastery.

The agent must never unlock Guided Mode itself. The backend owns this
policy.

### E. Turn Management and synchronous text workflow

Phase 1 turn flow:

1.  Frontend submits a candidate answer.
2.  FastAPI validates the active session and request.
3.  Backend persists the candidate answer first.
4.  Backend invokes the Interviewer Agent through the approved
    graph/tool integration.
5.  Agent produces the next interviewer response or action.
6.  Backend validates and persists the interviewer turn.
7.  FastAPI returns the response to the frontend.

Design:

-   Turn IDs and sequence numbers.
-   Idempotency keys.
-   Duplicate submission handling.
-   Persistence ordering.
-   Concurrent request handling.
-   Timeout and retry behavior.
-   Recovery when the candidate answer is saved but agent generation
    fails.
-   Recovery when agent output is generated but persistence fails.

Do not put each live interview turn onto NATS in Phase 1.

### F. Session context package

Specify the exact input contract used to initialize or resume an
interview:

-   Authenticated user context supplied by backend.
-   Active track and track type.
-   Interview Brief version.
-   Candidate profile snapshot.
-   Track memory summary.
-   Question history.
-   Session metadata.
-   Interview mode.
-   Constraints such as time, coverage and turn limits.

Use compact relevant context rather than sending all prior transcripts
by default.

### G. Question history and repeat avoidance

Coordinate with Member 4 on ownership of detailed history persistence
and memory updates.

Specify how the Interviewer consumes:

-   Previously asked questions.
-   Question fingerprints.
-   Competency coverage history.
-   Questions deliberately revisited in Guided mode.
-   Strict-mode repeat avoidance.

Avoid exact repeats in Strict mode where possible, while allowing useful
revisiting of a concept through a different question or problem.

### H. Voice extension --- Phase 2 design only

Document the intended extension points without making Phase 1 depend on
voice technology.

Include:

-   Browser audio streaming.
-   Server-side Speech Gateway.
-   ASR/TTS integration boundary.
-   Pause, interruption and reconnect behavior.
-   Transcript correction.
-   Optional audio retention and consent.
-   Text fallback.
-   Latency and compute metrics.

Do not finalize ASR/TTS vendors or protocols unless the team makes a
separate decision.

## 6.3 LangGraph design requirements

Document:

-   Typed Interviewer graph state.
-   Graph nodes and node responsibilities.
-   Conditional routing for Strict and Guided behavior.
-   Routing for follow-up, next question, assistance and closure.
-   Tool contracts.
-   Graph input/output.
-   Checkpointing and recovery.
-   Error handling.
-   How graph execution maps to the backend session lifecycle.
-   How state is isolated by user, track and session.

The graph must not become the authoritative owner of session status.
Backend services validate and persist lifecycle transitions.

## 6.4 Required diagrams

1.  Complete interview session state machine.
2.  Session creation sequence diagram.
3.  Text interview turn sequence diagram.
4.  Interviewer LangGraph workflow.
5.  Strict versus Guided behavior diagram.
6.  Guided hint/explanation sequence diagram.
7.  Pause/resume and recovery sequence diagram.
8.  Phase 2 voice extension component diagram.

## 6.5 Required API and schema deliverables

-   Session creation API.
-   Session retrieval API.
-   Submit-answer/turn API.
-   Pause/resume API.
-   Finish-interview API.
-   Interview turn request/response schema.
-   Session metadata schema.
-   Interviewer graph state schema.
-   Strict/Guided mode contract.
-   Question and answer metadata schema.
-   Idempotency and error response specification.

## 6.6 Member 3 completion criteria

-   Full text interview lifecycle is documented.
-   Strict and Guided modes are clearly distinguished.
-   Backend, not the agent, controls eligibility and session state.
-   Candidate answers are durably persisted before the agent is invoked.
-   Duplicate turns and partial failures have recovery behavior.
-   The Interviewer graph uses the correct track and brief context.
-   Phase 2 voice can be added without redesigning the Phase 1 interview
    core.

------------------------------------------------------------------------

# 7. Member 4 --- Assessment, Feedback & Progression

## 7.1 Objective

Design how completed interview sessions are evaluated, how
evidence-based feedback is generated, how track memory is updated and
how Strict/Guided progression is determined. Design the Feedback Agent
using LangGraph.

## 7.2 Modules owned

### A. Feedback processing workflow

Design the asynchronous completion workflow:

1.  Backend receives the finish-interview request.
2.  Backend validates the session and moves it to `COMPLETING`.
3.  Backend verifies transcript durability.
4.  Backend creates a feedback job in PostgreSQL.
5.  Backend publishes the job to NATS JetStream.
6.  Worker validates the job against PostgreSQL.
7.  Worker loads the exact session context.
8.  Feedback Agent evaluates the session.
9.  Detailed report is saved in MongoDB.
10. Structured assessment summary is saved in PostgreSQL.
11. Track memory and question history are updated.
12. Backend evaluates progression policy.
13. Backend marks the session `COMPLETED` and notifies the frontend.

The session must not be marked complete until durable transcript and
feedback persistence are confirmed.

### B. Feedback Agent

Design the Feedback Agent as a LangGraph workflow.

Inputs should include:

-   Exact completed session transcript.
-   Session metadata and mode.
-   Candidate profile snapshot.
-   Interview Brief version used by the session.
-   Relevant session artifacts.
-   Relevant track context.

The graph should:

1.  Load and validate the completed session context.
2.  Identify questions and corresponding candidate answers.
3.  Extract evidence from the exact transcript.
4.  Evaluate relevant competencies.
5.  Record strengths and improvement areas.
6.  Determine confidence and evidence sufficiency.
7.  Mark unsupported areas as `NOT_ASSESSED`.
8.  Generate actionable recommendations.
9.  Validate the report structure.
10. Save the detailed report and structured summary through backend
    tools.

### C. Evidence-based assessment

Specify the assessment methodology and output schema.

For each question or competency, document:

-   Competency/topic.
-   Question reference.
-   Candidate answer/turn reference.
-   Evidence excerpt or turn reference.
-   Observation.
-   Assessment result.
-   Confidence.
-   Evidence sufficiency.
-   Whether assistance was used.
-   Recommendation, where appropriate.

Do not assess a competency merely because it was not asked. Unassessed
topics are not failures.

Do not infer personality, worth or hiring outcomes. The platform reports
observed interview evidence and preparation opportunities.

### D. Feedback Report

Design the detailed report structure, including:

-   Session summary.
-   Interview mode.
-   Competencies assessed.
-   Question-level observations.
-   Strengths.
-   Improvement areas.
-   Unassessed topics.
-   Evidence references.
-   Confidence and evidence limitations.
-   Actionable recommendations.
-   Suggested learning priorities.
-   Relevant next steps.

The report must be grounded in the exact session and its versioned
context. Avoid unsupported generalizations.

### E. Track Memory and Question History updates

Coordinate with Member 2 on track-level data contracts and Member 3 on
question-history consumption.

Design updates for:

-   Assessed topics.
-   Not-assessed topics.
-   Competency evidence.
-   Session summaries.
-   Question history and fingerprints.
-   Learning priorities.
-   Current Interview Brief reference.
-   Strict versus Guided evidence metadata.

Use compact summaries for future sessions. Do not automatically inject
all previous transcripts into every interview.

### F. Strict/Guided progression policy

The HLD baseline is:

-   Every new track starts with Strict Interviews.
-   Count completed Strict sessions per track only.
-   After three completed Strict attempts in a particular track,
    evaluate aggregate evidence.
-   Guided becomes available only if performance is consistently
    insufficient under the policy.
-   If evidence is insufficient to make that determination, do not label
    the candidate weak; collect more evidence or leave the decision
    pending.
-   Once unlocked, Guided remains available.
-   Strict remains available.
-   Guided sessions do not count toward the initial unaided Strict
    baseline.

Design:

-   Per-track attempt counting.
-   Definition of a completed Strict attempt.
-   Aggregation of evidence across the three sessions.
-   Consistently-insufficient evaluation policy.
-   Pending/insufficient-evidence behavior.
-   Eligibility state and transition rules.
-   Audit trail and explanation of the decision.
-   Protection against duplicate completion events.
-   Backend enforcement.

The actual numerical thresholds and calibration are open decisions in
the HLD. Do not invent final thresholds and present them as approved.
Document proposed options separately for team review.

### G. NATS worker and failure handling

Design the feedback worker behavior:

-   Job validation against PostgreSQL.
-   Idempotency.
-   At-least-once message delivery.
-   Acknowledgment timing.
-   Retry/backoff.
-   Dead-letter behavior.
-   Duplicate feedback job handling.
-   Partial persistence recovery.
-   Reconciliation between MongoDB detailed report and PostgreSQL
    summary.
-   Notification only after the required durable writes succeed.

### H. Feedback and assessment data ownership

Coordinate the split:

-   Detailed feedback report and detailed conversation-related history:
    MongoDB.
-   Structured assessment summary and progression state: PostgreSQL.
-   Track memory and question history: MongoDB, with any required
    authoritative lifecycle metadata in PostgreSQL.
-   Job lifecycle and authorization mapping: PostgreSQL.

## 7.3 LangGraph design requirements

Document:

-   Typed Feedback graph state.
-   Nodes for context loading, evidence extraction, assessment, report
    generation, validation and persistence requests.
-   Conditional paths for missing transcript, insufficient evidence and
    validation failure.
-   Tool contracts.
-   Graph input/output schema.
-   Checkpoint and retry behavior.
-   Graph versioning.
-   How a worker invokes the graph.
-   How graph output is validated before backend persistence.

The Feedback Agent must not directly update eligibility or write to
databases. It returns assessment results through approved backend tools;
backend policy code makes the final progression decision.

## 7.4 Required diagrams

1.  Feedback processing sequence diagram.
2.  Feedback Agent LangGraph workflow.
3.  Evidence extraction and assessment flow.
4.  Feedback report data model.
5.  Track memory update sequence diagram.
6.  Strict/Guided progression state machine.
7.  NATS feedback job retry and dead-letter flow.
8.  Cross-database persistence and reconciliation diagram.

## 7.5 Required API, event and schema deliverables

-   Finish-interview/feedback job contract in coordination with Member
    3.
-   Feedback job event schema.
-   Feedback Agent graph state schema.
-   Detailed feedback report JSON schema.
-   Structured assessment summary schema.
-   Question-level evidence schema.
-   Competency assessment schema.
-   Track memory update contract.
-   Question history update contract.
-   Strict/Guided eligibility state and policy specification.
-   Feedback status retrieval API or integration contract.

## 7.6 Member 4 completion criteria

-   Feedback is generated from the exact completed session and correct
    versioned context.
-   Every assessment is evidence-linked.
-   `NOT_ASSESSED` is supported.
-   Guided assistance is distinguished from independent evidence.
-   Detailed report and structured summary have clear storage ownership.
-   Progression is per track and backend-enforced.
-   Three-Strict-attempt logic handles insufficient evidence safely.
-   Async retries and duplicate jobs do not create duplicate or
    inconsistent results.

------------------------------------------------------------------------

# 8. Shared integration contracts

These contracts must be agreed upon by all four members before
finalizing individual LLDs.

## 8.1 Common identifiers

Use consistent identifiers and document their types and generation
rules:

-   `user_id`
-   `track_id`
-   `session_id`
-   `document_id`
-   `job_id`
-   `correlation_id`
-   `turn_id`
-   `profile_version_id` or equivalent profile version reference
-   `interview_brief_version_id` or equivalent brief version reference
-   `llm_call_id`

The final naming and ID-generation conventions should be recorded in the
shared standards document.

## 8.2 Common agent invocation contract

All agents should use a common invocation envelope. At minimum, define:

-   Agent name and graph version.
-   Operation name.
-   Authenticated backend context.
-   Correlation ID.
-   Relevant entity IDs.
-   Validated input payload.
-   Graph execution/checkpoint reference, if used.
-   Structured result.
-   Error/status representation.

Do not pass secrets or trust a user ID supplied by the model. Backend
identity is authoritative.

## 8.3 Common tool contract

For every tool, document:

  Field                 Requirement
  --------------------- ------------------------------------------
  Tool name             Stable and unique
  Owning module         Member responsible
  Allowed agent         Explicit allowlist
  Purpose               One clear backend operation
  Input schema          Typed and validated
  Output schema         Typed and validated
  Authorization         Ownership and scope checks
  State preconditions   Required lifecycle state
  Side effects          Database/event changes
  Idempotency           Required behavior for retries
  Errors                Stable error codes and recovery behavior
  Audit                 Whether operation must be recorded

## 8.4 Common API response and error conventions

Agree on:

-   Success response envelope.
-   Validation error format.
-   Authentication and authorization errors.
-   Not-found behavior.
-   Conflict/state-transition errors.
-   Rate-limit and timeout errors.
-   Retryable versus non-retryable errors.
-   Correlation ID propagation.

Do not let each member invent a different response format.

## 8.5 Cross-module handoffs

  -----------------------------------------------------------------------
  From                    To                      Handoff
  ----------------------- ----------------------- -----------------------
  Member 1                All members             Identity context,
                                                  database conventions,
                                                  Agent Tool Layer, LLM
                                                  Gateway and event
                                                  standards

  Member 1                Member 2                Candidate context and
                                                  document/JD processing
                                                  interfaces

  Member 2                Member 3                Ready track, Interview
                                                  Brief version and track
                                                  context package

  Member 2                Member 4                Competency definitions
                                                  and Interview Brief
                                                  version

  Member 3                Member 4                Completed session,
                                                  transcript, mode and
                                                  versioned session
                                                  context

  Member 4                Member 2                Updated track memory
                                                  and learning priorities

  Member 4                Member 3                Updated question
                                                  history and progression
                                                  eligibility

  All members             Member 1 / integration  API, schema, tool and
                          owner                   event contract changes
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 9. Required LLD format for every member

Every member must submit their module using the following structure.

## 9.1 Document sections

1.  **Module Overview**
    -   Purpose.
    -   Scope.
    -   Responsibilities.
    -   Out-of-scope items.
    -   Dependencies.
2.  **Component Design**
    -   Components and responsibilities.
    -   Internal interfaces.
    -   Component interaction diagram.
3.  **API Design**
    -   Endpoint and HTTP method.
    -   Authentication requirement.
    -   Request schema.
    -   Response schema.
    -   Validation.
    -   Error codes.
    -   Idempotency, where applicable.
4.  **Database Design**
    -   Tables or collections.
    -   Field names and data types.
    -   Primary/foreign keys or document references.
    -   Constraints.
    -   Indexes.
    -   Ownership.
    -   Retention and versioning.
    -   Transaction and consistency behavior.
5.  **LangGraph Design**
    -   Graph purpose.
    -   Typed state schema.
    -   Nodes.
    -   Normal edges.
    -   Conditional edges.
    -   Tools and allowlists.
    -   Input/output contract.
    -   Checkpointing.
    -   Retry and failure paths.
    -   Graph versioning.
6.  **Workflow and Sequence Diagrams**
    -   Main success flow.
    -   Alternative flow.
    -   Failure/retry flow.
    -   Cross-module handoffs.
7.  **State Management**
    -   State definitions.
    -   Allowed transitions.
    -   Transition owner.
    -   Preconditions.
    -   Invalid transition behavior.
8.  **Security and Privacy**
    -   Authentication.
    -   Authorization.
    -   Ownership and isolation.
    -   Untrusted input handling.
    -   Sensitive data handling.
    -   Audit events.
9.  **Error Handling and Recovery**
    -   Validation errors.
    -   Dependency failures.
    -   Timeouts.
    -   Retry policy.
    -   Idempotency.
    -   Partial failure recovery.
    -   Reconciliation.
10. **Observability**
    -   Logs.
    -   Metrics.
    -   Traces.
    -   Correlation IDs.
    -   LLM usage and cost metadata, where applicable.
11. **Testing Plan**
    -   Unit tests.
    -   Integration tests.
    -   API tests.
    -   Graph tests.
    -   Failure and retry tests.
    -   Authorization and isolation tests.
    -   Acceptance criteria.
12. **Open Decisions**
    -   Unresolved choices.
    -   Options.
    -   Recommendation.
    -   Decision owner.
    -   Impact if deferred.

## 9.2 Minimum implementation detail

A diagram alone is not an LLD. Every major component must include:

-   What it does.
-   Who invokes it.
-   What data it receives.
-   What it returns.
-   What it reads or writes.
-   Which module owns the operation.
-   What can fail.
-   How failure is handled.
-   How it is tested.

------------------------------------------------------------------------

# 10. Suggested repository structure

Create one shared LLD directory in the project repository.

``` text
LLD/
│
├── README.md
│
├── 00_Master_Architecture/
│   ├── architecture_decisions.md
│   ├── common_conventions.md
│   ├── langgraph_standards.md
│   ├── common_api_contracts.md
│   ├── common_tool_contracts.md
│   └── integration_contracts.md
│
├── 01_Platform_Data_Onboarding/
│   ├── module_overview.md
│   ├── authentication.md
│   ├── candidate_profile.md
│   ├── document_management.md
│   ├── database_design.md
│   ├── object_storage.md
│   ├── nats_jetstream.md
│   ├── llm_gateway_litellm.md
│   ├── agent_tool_layer.md
│   ├── onboarding_agent.md
│   ├── diagrams/
│   └── schemas/
│
├── 02_Track_Management/
│   ├── module_overview.md
│   ├── track_management.md
│   ├── track_creator_agent.md
│   ├── interview_brief.md
│   ├── preparation_plan.md
│   ├── company_jd_research.md
│   ├── track_memory_initialization.md
│   ├── diagrams/
│   └── schemas/
│
├── 03_Interview_Engine/
│   ├── module_overview.md
│   ├── session_management.md
│   ├── interviewer_agent.md
│   ├── strict_mode.md
│   ├── guided_mode.md
│   ├── turn_management.md
│   ├── session_context.md
│   ├── voice_phase2.md
│   ├── diagrams/
│   └── schemas/
│
├── 04_Assessment_Feedback/
│   ├── module_overview.md
│   ├── feedback_workflow.md
│   ├── feedback_agent.md
│   ├── assessment_methodology.md
│   ├── feedback_report.md
│   ├── track_memory_updates.md
│   ├── progression_policy.md
│   ├── nats_feedback_worker.md
│   ├── diagrams/
│   └── schemas/
│
└── 05_Integration_Review/
    ├── api_contract_review.md
    ├── database_contract_review.md
    ├── graph_integration_review.md
    ├── end_to_end_workflows.md
    └── open_decisions_register.md
```

------------------------------------------------------------------------

# 11. Suggested 10-working-day schedule

  -----------------------------------------------------------------------
  Day                     All-team activity       Expected result
  ----------------------- ----------------------- -----------------------
  1                       Review HLD and confirm  Agreed ownership and
                          module boundaries       dependencies

  2                       Member 1 publishes      Common contracts draft
                          shared conventions; all
                          members identify
                          interfaces

  3--4                    Individual component,   Module design drafts
                          database and API design

  5--6                    LangGraph nodes, state, Agent graph designs
                          edges, tools and
                          workflows

  7                       Sequence diagrams,      End-to-end module flows
                          lifecycle and failure
                          handling

  8                       Security, observability Operational design
                          and testing design

  9                       Cross-member            Resolved interface
                          integration review      conflicts

  10                      Consolidation and HLD   Final integrated LLD
                          traceability review
  -----------------------------------------------------------------------

If the team has more time, use it to validate schemas and workflows with
small prototypes rather than expanding the scope unnecessarily.

------------------------------------------------------------------------

# 12. Final integration checklist

The LLD is ready for implementation review only when these items are
checked.

## Architecture

-   [ ] Four logical agents match the HLD.
-   [ ] LangGraph is used for agent workflow orchestration.
-   [ ] FastAPI remains the backend modular monolith.
-   [ ] All agents use the Agent Tool Layer.
-   [ ] All model calls go through LiteLLM via the LLM Gateway.
-   [ ] No agent directly accesses databases or object storage.
-   [ ] PostgreSQL and MongoDB responsibilities are clearly separated.
-   [ ] NATS is used for asynchronous jobs, not every live interview
    turn.

## Data and contracts

-   [ ] Common identifiers are consistent.
-   [ ] API response and error conventions are shared.
-   [ ] Database schemas have clear ownership.
-   [ ] Agent state schemas are defined.
-   [ ] Tool schemas and allowlists are defined.
-   [ ] Interview Brief and profile versions are preserved with
    sessions.
-   [ ] Track isolation is enforced.

## Interview and assessment rules

-   [ ] New tracks start in Strict mode.
-   [ ] Guided eligibility is enforced by backend policy.
-   [ ] Three completed Strict attempts are counted per track.
-   [ ] Guided sessions do not count as independent Strict evidence.
-   [ ] Insufficient evidence is not treated as failure.
-   [ ] Assessments reference exact session evidence.
-   [ ] Unassessed competencies are explicitly represented.
-   [ ] Session completion waits for durable feedback persistence.

## Reliability and security

-   [ ] Idempotency is defined for important operations.
-   [ ] Retry and dead-letter behavior is specified.
-   [ ] Cross-database reconciliation is documented.
-   [ ] Ownership checks exist for every tool operation.
-   [ ] Untrusted resumes, JDs and external content are treated as data.
-   [ ] Logs and traces carry correlation IDs.
-   [ ] Privacy-aware LLM usage logging is defined.

------------------------------------------------------------------------

# 13. Final instruction to the team

Each member should work independently on their assigned module, but all
four must use the same architecture conventions and integration
contracts.

**Do not start implementation based only on individual module drafts.**
First consolidate the LLD, review cross-module interfaces, resolve
conflicting schemas and verify the end-to-end workflows.

The intended outcome is one coherent, implementation-ready LLD that
follows the HLD and uses LangGraph without allowing the orchestration
framework to take ownership of backend business rules or persistent
application state.
