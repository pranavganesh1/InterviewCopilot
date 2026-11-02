# InterviewCopilot — Member 2 Low-Level Design
## Track Management & Track Creator Agent

**Document type:** Low-Level Design (LLD)  
**Module owner:** Member 2  
**Architecture baseline:** InterviewCopilot HLD v0.2, dated 31 October 2026  
**Orchestration framework:** LangGraph  
**Backend:** FastAPI modular monolith  
**Data stores:** PostgreSQL, MongoDB and S3-compatible object storage  
**Asynchronous processing:** NATS JetStream  
**LLM access:** InterviewCopilot LLM Gateway backed by LiteLLM Proxy  
**Status:** Detailed design proposal for team review

---

# 1. Purpose

This document defines the Low-Level Design for Track Management and the Track Creator Agent.

Member 2 owns the preparation workflow that converts a candidate's chosen preparation objective into an independent, reusable Preparation Track. The Track Creator Agent produces a structured preparation plan, competency coverage, research references where relevant, and a versioned Interview Brief that the Interviewer and Feedback Agents can consume.

The design covers:

1. Track creation, retrieval, update, archive and refresh.
2. The three preparation paths: topic-based, role-based and company/JD-based.
3. Track lifecycle and readiness.
4. Track Creator Agent implemented using LangGraph.
5. Candidate context selection for a particular track.
6. Job description and public company/role research workflow.
7. Competency mapping and preparation plan creation.
8. Interview Brief schema and versioning.
9. Initial track context, memory and question-history references.
10. API, database, event, security, retry and testing design.

## 1.1 Ownership boundaries

| Component | Owner | Member 2 responsibility |
|---|---|---|
| Authentication and user identity | Member 1 | Consume trusted backend identity |
| Candidate Profile | Member 1 | Read selected candidate context through approved tools |
| Document upload and processing | Member 1 | Consume processed JD/document references |
| Track Management | Member 2 | Full ownership |
| Track Creator LangGraph | Member 2 | Full ownership |
| Interview Brief and versioning | Member 2 | Full ownership |
| Preparation plan and competency coverage | Member 2 | Full ownership |
| Company/JD research workflow | Member 2 | Full ownership |
| Track memory updates after feedback | Member 4/shared | Define initial context and read/update interfaces; do not own assessment-driven updates |
| Question history persistence/update | Member 4/shared | Consume for context and establish initial track reference |
| Interview sessions and live questioning | Member 3 | Provide brief and track context contract |
| Feedback and assessment | Member 4 | Provide competency/rubric contract |
| LLM Gateway, Agent Tool Layer, NATS platform | Member 1 | Use shared infrastructure |

Member 2 must not implement a separate user identity system, database access path, LLM client or tool-security layer.

---

# 2. Product concepts and supported preparation paths

A Preparation Track represents one continuing preparation objective. A candidate may have multiple independent tracks. Each track has its own preparation configuration, Interview Brief, sessions, question history, memory, assessment evidence and Strict/Guided eligibility.

The Candidate Context Vault is shared across tracks. Track-specific history and mode eligibility are not shared.

## 2.1 Path A — Topic-based preparation

The candidate wants to prepare for a subject or collection of topics without necessarily targeting a specific employer.

Examples:

- Data Structures & Algorithms.
- System Design.
- DBMS.
- Digital Electronics.
- Thermodynamics.
- Financial Accounting.

Suggested inputs:

| Input | Required? | Description |
|---|---:|---|
| Subject/topic | Yes | Main preparation area |
| Selected subtopics | Optional | Topics to emphasize |
| Current experience level | Optional | Candidate self-report; not assessed fact |
| Desired difficulty | Optional | Requested challenge level |
| Interview duration | Optional | Desired session duration |
| Interview objective | Optional | Assess current knowledge, practice, revise or simulate |
| Interview style/role context | Optional | Additional framing |

A materially different subject should normally be a separate track.

## 2.2 Path B — Role-based preparation

The candidate is preparing for a professional role without selecting a particular company.

Examples:

- Software Engineer Intern.
- Backend Engineer.
- Data Analyst.
- Embedded Systems Engineer.
- Mechanical Design Engineer.
- Financial Analyst.

Suggested inputs:

- Target role.
- Career stage or experience level.
- Academic background or relevant profile context.
- Optional preferred industry.
- Optional JD.
- Relevant topics or skills.
- Desired duration and difficulty.

The Track Creator should distinguish general role expectations from requirements derived from a specific employer's JD. It must not imply that generic role information is a particular company's official rubric.

## 2.3 Path C — Company/JD-based preparation

The candidate is preparing for a particular company, role and opportunity.

Suggested inputs:

- Company name.
- Target role/title.
- JD text or uploaded JD document.
- Interview stage, if known.
- Expected interview date, if known.
- Topics the candidate wants to prioritize.

Possible stages:

- Online assessment.
- Technical screening.
- DSA/coding round.
- Project discussion.
- System design or domain-specific technical round.
- Managerial round.
- HR/behavioral round.
- Unknown/full-process simulation.

Company research should use relevant public information and retain source references. The system must not claim access to confidential interview questions, internal hiring rubrics or non-public company information.

## 2.4 Track identity and reuse

Reuse an existing track when the preparation objective remains materially compatible.

For company-specific preparation, track identity should consider:

- Company.
- Role.
- JD/opportunity version.
- Selected interview objective or stage.

Create a separate track or a new explicit version when the student changes to a substantially different subject, role, company opportunity or JD. Preserve historical reports and assessments rather than rewriting them against new requirements.

---

# 3. Fixed architecture decisions

| Concern | Selected direction |
|---|---|
| Backend | FastAPI modular monolith |
| Agent orchestration | **LangGraph** |
| Model integration | InterviewCopilot LLM Gateway backed by LiteLLM |
| Structured application state | PostgreSQL |
| Track memory and question history | MongoDB |
| Uploaded JD/document binaries | S3-compatible object storage |
| Asynchronous jobs | NATS JetStream |
| Agent access | Controlled backend Agent Tool Layer |
| Logical agents | Onboarding, Track Creator, Interviewer and Feedback |
| Phase 1 interview runtime | Text |
| Phase 2 | Server-side streaming voice |

## 3.1 Non-negotiable rules

1. PostgreSQL is authoritative for track ownership, lifecycle, current version pointers and structured preparation metadata.
2. MongoDB stores track memory, question history and detailed conversational content according to the shared collection conventions.
3. Uploaded JD files remain in object storage; PostgreSQL stores metadata and storage references.
4. The Track Creator graph cannot connect directly to PostgreSQL, MongoDB or object storage.
5. All model calls go through the InterviewCopilot LLM Gateway and LiteLLM.
6. The Track Creator's tools are restricted to its approved allowlist.
7. The backend derives `user_id` from trusted authentication context.
8. Backend services enforce track ownership, valid state transitions and version changes.
9. The Track Creator runs for a new track or material refresh. It does not run every time a candidate starts a session in a valid existing track.
10. Existing valid tracks reuse their current Interview Brief and track memory.
11. Candidate profile changes do not silently rewrite old Interview Briefs or completed reports.
12. Every session stores the candidate profile version/snapshot and Interview Brief version it used.
13. Treat resumes, JDs and retrieved public content as untrusted data, not as instructions to the graph.
14. Do not add a separate vector database in Phase 1; exact fingerprints and metadata are sufficient for initial question-history handling.

---

# 4. Component architecture

```mermaid
flowchart TB
    Candidate[Candidate]
    UI[Web Frontend]
    API[FastAPI API Layer]

    subgraph TrackModule[Track Management Module]
        Service[Track Service]
        Validator[Track Input / State Validator]
        Context[Candidate Context Selector]
        Brief[Interview Brief Version Service]
        Prep[Preparation Plan Service]
    end

    subgraph Creator[Track Creator — LangGraph]
        Start[Start / Refresh Graph]
        Analyze[Analyze Objective]
        Profile[Select Candidate Context]
        JD[Analyze JD]
        Research[Research Company / Role]
        Competency[Build Competency Coverage]
        Plan[Build Preparation Plan]
        Compose[Compose Interview Brief]
        Validate[Validate Structured Output]
    end

    Tools[Agent Tool Layer]
    Gateway[InterviewCopilot LLM Gateway]
    LiteLLM[LiteLLM Proxy]
    Models[Approved LLM Providers]

    PG[(PostgreSQL)]
    Mongo[(MongoDB)]
    S3[(Object Storage)]
    NATS[NATS JetStream]
    Workers[Preparation / Research Workers]

    Candidate --> UI --> API --> Service
    Service --> Validator
    Service --> PG
    Service --> Context
    Context --> PG
    Context --> Mongo
    Service --> Start
    Start --> Analyze --> Profile --> JD --> Research --> Competency --> Plan --> Compose --> Validate
    Creator --> Tools
    Tools --> Service
    Creator --> Gateway --> LiteLLM --> Models
    Service --> Brief --> PG
    Service --> Prep --> PG
    Service --> NATS --> Workers
    Workers --> S3
    Workers --> PG
    Workers --> Mongo
```

## 4.1 Component responsibilities

| Component | Responsibility |
|---|---|
| Track API | Frontend-facing track endpoints |
| Track Service | Track creation, state, ownership, refresh and version coordination |
| Track Input Validator | Validates topic/role/company/JD input |
| Candidate Context Selector | Selects relevant profile fields for this track |
| Track Creator Graph | Generates competencies, plan, research references and Interview Brief |
| Interview Brief Service | Validates and versions brief artifacts |
| Preparation Plan Service | Persists the structured preparation plan |
| Agent Tool Layer | Validates graph tool permissions and executes backend operations |
| LLM Gateway | Central model routing and usage capture |
| NATS | Async preparation/research/document jobs |
| PostgreSQL | Authoritative track metadata and lifecycle |
| MongoDB | Track memory and question history |
| Object Storage | Original JD and supporting documents |

---

# 5. Track lifecycle and state management

## 5.1 HLD lifecycle

Use the HLD track lifecycle as the baseline:

```text
DRAFT -> PREPARING -> READY -> ACTIVE
```

Other states:

- `PREPARATION_FAILED`
- `NEEDS_REFRESH`
- `PAUSED`
- `ARCHIVED`

## 5.2 State definitions

| State | Meaning |
|---|---|
| `DRAFT` | Track metadata exists, but preparation has not started |
| `PREPARING` | Track Creator and/or preparation jobs are working |
| `READY` | Required preparation artifacts and a valid Interview Brief exist |
| `ACTIVE` | Track is being used for interview preparation/sessions |
| `PREPARATION_FAILED` | Preparation failed and requires retry or user action |
| `NEEDS_REFRESH` | Existing preparation may be stale because a material input changed |
| `PAUSED` | Candidate has paused the track |
| `ARCHIVED` | Candidate has archived the track; historical data remains |

## 5.3 State diagram

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PREPARING: create / prepare
    PREPARING --> READY: artifacts validated and saved
    PREPARING --> PREPARATION_FAILED: unrecoverable preparation error
    PREPARATION_FAILED --> PREPARING: retry / edit input
    READY --> ACTIVE: start session or activate track
    ACTIVE --> READY: no active session / ready state
    READY --> NEEDS_REFRESH: material input changes
    ACTIVE --> NEEDS_REFRESH: material input changes
    NEEDS_REFRESH --> PREPARING: refresh accepted
    READY --> PAUSED
    ACTIVE --> PAUSED
    PAUSED --> READY: resume
    PAUSED --> ACTIVE: resume
    DRAFT --> ARCHIVED
    READY --> ARCHIVED
    ACTIVE --> ARCHIVED
    PAUSED --> ARCHIVED
    NEEDS_REFRESH --> ARCHIVED
    PREPARATION_FAILED --> ARCHIVED
    ARCHIVED --> [*]
```

The precise `READY`/`ACTIVE` semantics and whether archiving is allowed while a session is active must be finalized with Member 3. The track service must not change an active interview session's context.

## 5.4 Transition rules

- Only the Track Service may update the track lifecycle.
- Only the authenticated owner may create/update/archive their track.
- A track cannot become `READY` until required preparation artifacts are validated and persisted.
- A track cannot become `ACTIVE` unless it is usable and not archived.
- A refresh creates a new Interview Brief version; it must not overwrite an old version.
- A track in `NEEDS_REFRESH` may retain old sessions and reports.
- Existing sessions keep their captured profile and brief versions.
- Archive must preserve historical sessions, reports, memory and audit history.
- Failed preparation can be retried without creating a duplicate track or duplicate brief version.

---

# 6. Track creation and refresh workflows

## 6.1 New track creation

### Preconditions

- Authenticated user exists.
- Input matches one supported preparation path.
- Required topic/role/company information is present.
- Any supplied JD reference belongs to the authenticated user and is accessible.
- Candidate context can be retrieved.
- No conflicting duplicate request is currently being processed.

### Sequence diagram

```mermaid
sequenceDiagram
    actor Candidate
    participant UI as Frontend
    participant API as FastAPI
    participant TS as Track Service
    participant PG as PostgreSQL
    participant CB as Candidate Context Builder
    participant G as Track Creator LangGraph
    participant GW as LLM Gateway

    Candidate->>UI: Choose topic / role / company-JD path
    UI->>API: POST /tracks
    API->>TS: Validate request + trusted user context
    TS->>PG: Create DRAFT track and request record
    TS->>PG: Transition DRAFT -> PREPARING
    TS->>CB: Select relevant candidate context
    CB->>PG: Load exact current profile version
    CB-->>TS: Candidate context snapshot/reference
    TS->>G: Invoke Track Creator graph
    G->>GW: Analyze objective and generate preparation artifacts
    GW-->>G: Structured outputs
    G-->>TS: Preparation plan + competencies + brief draft
    TS->>PG: Validate and persist versioned artifacts
    TS->>PG: Transition PREPARING -> READY
    TS-->>API: Track ready
    API-->>UI: Track and preparation summary
```

The graph's generated result is not automatically authoritative. Track Service validates the structure, ownership and completeness before committing the final records.

## 6.2 Refresh existing track

A refresh is required when the preparation objective materially changes or relevant context becomes stale.

Examples:

- JD or target role changes materially.
- Selected topics change materially.
- Relevant candidate profile changes.
- Company research becomes stale.
- Candidate explicitly requests a preparation refresh.

### Refresh rules

1. Do not silently modify the old Interview Brief.
2. Record the refresh reason and triggering input version.
3. Preserve the current brief while new preparation is in progress, if it remains safe to use.
4. Generate a new brief version.
5. Validate and save the new version.
6. Advance the track's current brief pointer only after successful persistence.
7. Old sessions continue to reference the brief version they originally used.
8. If refresh fails, retain the last valid brief and expose the failure state.
9. Do not invoke Track Creator for an ordinary new interview session.

### Refresh sequence

```mermaid
sequenceDiagram
    actor Candidate
    participant API as FastAPI
    participant TS as Track Service
    participant PG as PostgreSQL
    participant G as Track Creator LangGraph
    participant GW as LLM Gateway

    Candidate->>API: Request track refresh
    API->>TS: Refresh request + reason
    TS->>PG: Verify ownership and current track version
    TS->>PG: Mark NEEDS_REFRESH / PREPARING
    TS->>G: Invoke refresh graph with prior context
    G->>GW: Re-evaluate changed objective and inputs
    GW-->>G: New preparation artifacts
    G-->>TS: New brief and plan draft
    TS->>TS: Validate outputs and references
    TS->>PG: Save new version; update current pointer
    TS->>PG: Mark READY
    TS-->>API: Refresh completed
```

## 6.3 New track versus new session

| User action | Track Creator behavior |
|---|---|
| Create new topic/role/company track | Invoke |
| Start another session in valid existing track | Do not invoke; reuse brief and memory |
| JD changes materially | Refresh or create a new track/version based on product policy |
| Target role changes materially | Refresh or create a new track/version |
| Selected topics change materially | Refresh |
| Relevant candidate profile changes | Mark potentially `NEEDS_REFRESH`; do not silently rewrite old brief |
| Company research becomes stale | Refresh relevant research if required |
| Candidate only changes interview duration for one session | Usually do not rebuild the whole track; pass session-specific constraint to Member 3 |

---

# 7. Track input and configuration model

## 7.1 Common track fields

Proposed fields:

- Track name.
- Track type (`TOPIC`, `ROLE`, `COMPANY_JD`).
- Preparation objective.
- Candidate-selected preferences.
- Relevant profile version/reference.
- Target interview stage, if known.
- Desired difficulty, if supplied.
- Default interview duration, if supplied.
- Current Track state.
- Current Interview Brief version pointer.
- Current preparation plan version pointer.
- Refresh metadata.

Avoid storing transient UI state as part of the durable track record.

## 7.2 Track creation request schema

Illustrative common request:

```json
{
  "track_type": "TOPIC",
  "name": "Data Structures and Algorithms",
  "objective": "PRACTICE",
  "topic_config": {
    "subject": "Data Structures and Algorithms",
    "selected_topics": ["Arrays", "Trees", "Graphs"],
    "self_reported_level": "INTERMEDIATE"
  },
  "preferences": {
    "desired_difficulty": "MIXED",
    "default_duration_minutes": 30
  }
}
```

Topic, role and company/JD details are mutually constrained by `track_type`. Do not accept arbitrary mixed payloads without validation.

## 7.3 Topic-based request

```json
{
  "track_type": "TOPIC",
  "name": "DBMS Preparation",
  "objective": "ASSESS_CURRENT_KNOWLEDGE",
  "topic_config": {
    "subject": "DBMS",
    "selected_topics": ["Normalization", "Indexing", "Transactions"],
    "self_reported_level": "BEGINNER"
  },
  "preferences": {
    "desired_difficulty": "MIXED",
    "default_duration_minutes": 25
  }
}
```

## 7.4 Role-based request

```json
{
  "track_type": "ROLE",
  "name": "Backend Engineer Intern",
  "objective": "INTERVIEW_SIMULATION",
  "role_config": {
    "target_role": "Backend Engineer Intern",
    "career_stage": "STUDENT",
    "preferred_industry": null,
    "relevant_topics": ["Python", "Databases", "APIs"]
  },
  "preferences": {
    "desired_difficulty": "MIXED",
    "default_duration_minutes": 35
  }
}
```

## 7.5 Company/JD-based request

```json
{
  "track_type": "COMPANY_JD",
  "name": "Example Company - Backend Intern",
  "objective": "COMPANY_SPECIFIC_PREPARATION",
  "company_config": {
    "company_name": "Example Company",
    "target_role": "Backend Engineer Intern",
    "job_description_document_id": "document-uuid",
    "job_description_text": null,
    "interview_stage": "TECHNICAL_SCREENING",
    "expected_interview_date": null,
    "priority_topics": ["Python", "REST APIs"]
  },
  "preferences": {
    "desired_difficulty": "MIXED",
    "default_duration_minutes": 40
  }
}
```

Company names and values above are examples only. The actual schema should permit either a verified document reference or supplied JD text according to the document-processing contract.

## 7.6 Validation rules

- `track_type` must be one of the supported values.
- The corresponding type-specific configuration is required.
- Topic-based tracks require a meaningful subject/topic.
- Role-based tracks require a target role.
- Company/JD tracks require a company and role; JD may be optional if the product supports company/role-only preparation.
- A document ID must belong to the current user and be in an eligible processing state.
- Date fields must be valid and timezone semantics documented.
- Desired difficulty and duration must be within configured bounds.
- Candidate self-reported proficiency must remain labeled as self-reported.
- Duplicate submission must be handled using an idempotency key.

---

# 8. PostgreSQL data model

## 8.1 `preparation_tracks`

| Column | Suggested type | Meaning |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | Owner |
| `track_type` | VARCHAR/enum | `TOPIC`, `ROLE`, `COMPANY_JD` |
| `name` | VARCHAR | Display name |
| `objective` | VARCHAR | Preparation goal |
| `status` | VARCHAR/enum | HLD track lifecycle |
| `config` | JSONB | Validated type-specific configuration |
| `current_brief_version_id` | UUID nullable | Current valid Interview Brief |
| `current_plan_version_id` | UUID nullable | Current valid preparation plan |
| `source_profile_version_id` | UUID nullable | Profile version used for latest preparation |
| `refresh_required` | BOOLEAN | Whether current preparation may be stale |
| `created_at` | TIMESTAMPTZ | Creation |
| `updated_at` | TIMESTAMPTZ | Last update |
| `archived_at` | TIMESTAMPTZ nullable | Archive timestamp |

Recommended indexes:

- `(user_id, updated_at DESC)`.
- `(user_id, status)`.
- `(user_id, track_type)`.
- `(status, updated_at)` for operational workflows.

## 8.2 `track_versions`

A track's configuration and preparation requirements may evolve. Use version records to preserve what the track meant at a point in time.

| Column | Suggested type | Meaning |
|---|---|---|
| `id` | UUID | Version ID |
| `track_id` | UUID | Parent track |
| `version_number` | INTEGER | Sequential version |
| `config_snapshot` | JSONB | Track configuration at this version |
| `source_profile_version_id` | UUID nullable | Candidate profile source |
| `source_jd_document_id` | UUID nullable | JD document source |
| `refresh_reason` | VARCHAR nullable | New track / JD changed / profile changed / manual |
| `created_at` | TIMESTAMPTZ | Version timestamp |
| `created_by` | UUID nullable | Candidate/system actor |

Unique `(track_id, version_number)`.

## 8.3 `interview_brief_versions`

| Column | Suggested type | Meaning |
|---|---|---|
| `id` | UUID | Brief version ID |
| `track_id` | UUID | Parent track |
| `track_version_id` | UUID | Source track version |
| `version_number` | INTEGER | Brief version |
| `schema_version` | VARCHAR | JSON schema version |
| `brief_data` | JSONB | Structured Interview Brief |
| `status` | VARCHAR | Draft, validated, active or superseded |
| `source_profile_version_id` | UUID nullable | Candidate snapshot source |
| `created_at` | TIMESTAMPTZ | Creation |
| `created_by` | UUID nullable | System/candidate actor |

Unique `(track_id, version_number)`.

Historical brief versions must not be deleted or silently rewritten while sessions reference them.

## 8.4 `preparation_plan_versions`

| Column | Suggested type | Meaning |
|---|---|---|
| `id` | UUID | Plan version ID |
| `track_id` | UUID | Parent track |
| `brief_version_id` | UUID | Associated Interview Brief |
| `version_number` | INTEGER | Plan version |
| `plan_data` | JSONB | Structured preparation plan |
| `status` | VARCHAR | Draft, validated, active, superseded |
| `created_at` | TIMESTAMPTZ | Creation |

Unique `(track_id, version_number)`.

## 8.5 `track_research_sources`

| Column | Suggested type | Meaning |
|---|---|---|
| `id` | UUID | Source ID |
| `track_id` | UUID | Track |
| `brief_version_id` | UUID nullable | Brief using this source |
| `source_url` | TEXT | Public source URL |
| `title` | TEXT nullable | Page/document title |
| `publisher` | TEXT nullable | Publisher/site |
| `published_at` | TIMESTAMPTZ nullable | Source publication date if known |
| `retrieved_at` | TIMESTAMPTZ | Retrieval time |
| `source_type` | VARCHAR | Company, role, industry, official JD, etc. |
| `relevance_note` | TEXT | Why source matters |
| `verification_status` | VARCHAR | Retrieved, checked, stale, unavailable |
| `created_at` | TIMESTAMPTZ | Creation |

Do not invent publication dates or treat retrieval date as publication date.

## 8.6 `track_preparation_jobs`

Can be implemented as a domain-specific job table or mapped to Member 1's common background-job pattern.

Suggested fields:

- `id` / `job_id`
- `track_id`
- `user_id`
- `job_type` (`TRACK_CREATION`, `TRACK_REFRESH`, `COMPANY_RESEARCH`)
- `status`
- `attempt_count`
- `input_version_id`
- `correlation_id`
- `last_error_code`
- `created_at`
- `updated_at`
- `completed_at`

Use unique constraints to prevent duplicate processing for the same requested generation/version.

---

# 9. Interview Brief design

## 9.1 Purpose

The Interview Brief is the versioned preparation artifact that gives Interviewer and Feedback Agents a consistent definition of the interview objective.

It should be structured, inspectable, validated and reusable. Do not rely on one long unstructured prompt that is regenerated on every interview.

## 9.2 Required contents

| Section | Contents |
|---|---|
| Identity | Track ID, track version, brief version, schema version |
| Candidate summary | Relevant academic background, experience, projects and skills |
| Selected candidate evidence | Profile items relevant to the preparation objective |
| Preparation objective | Subject, role, company, JD and interview stage |
| Requirements | Required and preferred competencies from objective/JD |
| Company/role context | Relevant public research and source references |
| Competency map | Competencies, definitions, topics and importance |
| Interview blueprint | Sections, intended coverage, order and time allocation |
| Question strategy | Question categories, difficulty range and follow-up strategy |
| Evaluation rubric | Competencies and evidence criteria |
| Evidence requirements | What a sufficiently grounded response could demonstrate |
| Interview constraints | Duration, mode policy and session-specific constraints reference |
| Assumptions/limitations | Missing inputs, uncertain or general role expectations |
| Provenance | Source profile version, JD version and research source IDs |

## 9.3 Illustrative Interview Brief JSON

```json
{
  "brief_id": "brief-uuid",
  "schema_version": "1.0",
  "track_id": "track-uuid",
  "track_version_id": "track-version-uuid",
  "brief_version_id": "brief-version-uuid",
  "brief_version_number": 1,
  "track_type": "ROLE",
  "preparation_objective": {
    "target_role": "Backend Engineer Intern",
    "company": null,
    "subject": null,
    "interview_stage": "TECHNICAL_SCREENING",
    "objective": "INTERVIEW_SIMULATION"
  },
  "candidate_context": {
    "profile_version_id": "profile-version-uuid",
    "relevant_profile_items": [
      {
        "profile_item_id": "project-uuid",
        "item_type": "PROJECT",
        "relevance": "Candidate built a backend API project."
      }
    ]
  },
  "requirements": {
    "required_competencies": [],
    "preferred_competencies": []
  },
  "competencies": [
    {
      "competency_id": "competency-uuid",
      "name": "API design",
      "description": "Design and explain a clear API contract.",
      "topics": ["HTTP methods", "status codes", "validation"],
      "importance": "HIGH",
      "source": "ROLE_EXPECTATION"
    }
  ],
  "interview_blueprint": {
    "sections": [
      {
        "section_id": "section-1",
        "name": "Backend fundamentals",
        "competency_ids": ["competency-uuid"],
        "target_duration_minutes": 10,
        "question_categories": ["CONCEPTUAL", "SCENARIO"]
      }
    ],
    "total_target_duration_minutes": 35,
    "coverage_requirements": []
  },
  "question_strategy": {
    "difficulty_distribution": {
      "EASY": 0.25,
      "MEDIUM": 0.50,
      "HARD": 0.25
    },
    "follow_up_policy": "ADAPTIVE_WITH_COVERAGE"
  },
  "evaluation_rubric": {
    "rubric_version": "1",
    "competency_rubrics": []
  },
  "research_source_ids": [],
  "assumptions_and_limitations": [],
  "created_at": "2026-11-02T12:00:00Z"
}
```

The values above are examples only. The final schema must be agreed with Members 3 and 4. Difficulty distributions should be generated from validated configuration, not hard-coded for every track.

## 9.4 Versioning rules

- Each successful material preparation produces a new brief version.
- A brief version is immutable once referenced by an interview session.
- A session stores the exact `interview_brief_version_id`.
- Old assessment reports retain that reference.
- New profile edits do not mutate old briefs.
- New JD text/document version creates a new source reference and may require refresh.
- Current brief pointer advances only after new brief validation and persistence succeed.
- Failed refresh retains the previous valid brief and does not create a falsely `READY` track.

## 9.5 Brief validation

Before setting the track to `READY`, validate:

- Required identity/version fields.
- Track type matches objective fields.
- Candidate profile version reference is valid and belongs to the owner.
- Required competencies are present for the selected path.
- Competency IDs are unique within the brief.
- Blueprint references only defined competency IDs.
- Rubric references only defined competency IDs.
- Research source IDs exist and belong to the track/brief.
- Duration and difficulty fields are valid.
- Assumptions/limitations are explicit when required.
- JSON schema version is supported.
- No untrusted source text is treated as an agent instruction.

---

# 10. Competency mapping and preparation plan

## 10.1 Competency mapping

The Track Creator should translate the selected objective into a structured set of competencies.

For each competency, define:

- Stable `competency_id`.
- Display name.
- Description.
- Topic/subtopic mapping.
- Importance or priority.
- Source (`USER_SELECTED`, `JD_REQUIRED`, `ROLE_EXPECTATION`, `DOMAIN_PACK`).
- Required/preferred classification where relevant.
- Evidence criteria for the Feedback Agent.
- Related question categories.

A competency is a target area for preparation and interview coverage. It is not evidence that the candidate has mastered that area.

## 10.2 Source distinction

Clearly label the origin of each requirement:

| Source | Meaning |
|---|---|
| `USER_SELECTED` | Explicitly chosen by the candidate |
| `JD_REQUIRED` | Present in the supplied JD |
| `ROLE_EXPECTATION` | General role expectation, not employer-confirmed |
| `COMPANY_PUBLIC_SOURCE` | Supported by a retrieved public source |
| `DOMAIN_PACK` | Supplied by an approved domain-specific pack |
| `AGENT_INFERRED` | Proposed by the model; requires validation/clear labeling |

Do not silently convert an agent inference into an employer requirement.

## 10.3 Preparation Plan schema

Example:

```json
{
  "plan_id": "plan-uuid",
  "track_id": "track-uuid",
  "plan_version": 1,
  "brief_version_id": "brief-version-uuid",
  "learning_priorities": [
    {
      "priority_id": "priority-uuid",
      "competency_id": "competency-uuid",
      "topic": "Database indexing",
      "priority": "HIGH",
      "reason": "This topic is an important part of the selected preparation objective.",
      "recommended_activity": "Review index structures and trade-offs.",
      "completion_status": "NOT_STARTED"
    }
  ],
  "practice_areas": [],
  "recommended_sequence": [],
  "assumptions": [],
  "created_at": "2026-11-02T12:00:00Z"
}
```

The initial plan is based on the preparation objective and candidate context. Later learning-priority changes should be driven by Feedback Agent evidence and the track memory workflow owned with Member 4.

## 10.4 Candidate context selection

The entire Candidate Context Vault should not be copied into every Interview Brief.

Select only relevant profile information:

- Education relevant to the objective.
- Skills related to the target subject/role.
- Projects related to the target competencies.
- Internships or work experience relevant to the interview.
- Candidate-confirmed achievements where relevant.

Each selected item should retain a profile item/version reference and provenance. Avoid unsupported model-inferred personal claims.

---

# 11. Company and JD research workflow

## 11.1 Purpose

For company/JD tracks, the Track Creator may use supplied JD information and relevant public research to build the preparation context.

Research should be relevant to the selected company, role and opportunity. It must not claim access to confidential questions or internal hiring rubrics.

## 11.2 Inputs

- Company name.
- Target role.
- JD text or uploaded JD document reference, where available.
- Interview stage, if known.
- Candidate-selected priority topics.
- Candidate context relevant to the target role.

## 11.3 Research categories

Possible public-source categories:

- Official company careers/role pages.
- Official company product/technology pages.
- Public engineering/blog pages.
- Public company/industry information relevant to the role.
- Candidate-provided JD.
- Reputable public role/skill references, where relevant.

The exact research providers and browsing implementation are a separate integration decision. The Track Creator graph should depend on a research service/tool interface, not on one provider-specific SDK.

## 11.4 Source provenance

For each source, record:

- Source ID.
- URL.
- Title.
- Publisher/domain.
- Source type.
- Published date, if actually available.
- Retrieved timestamp.
- Relevance to the selected company/role.
- Short summary or supported facts.
- Verification status.
- Brief version that consumed the source.

Do not fabricate dates, quotes, company policies or interview experiences. Distinguish official employer statements from third-party commentary and general role expectations.

## 11.5 JD extraction

If a JD is uploaded:

1. Member 1's Document Management pipeline validates and processes the file.
2. Track Service retrieves the processed text/reference through an approved tool.
3. Track Creator extracts role requirements and competencies.
4. Validate extracted content against the original JD text/reference.
5. Retain source passages or location references where practical.
6. Label ambiguous or inferred requirements.
7. Ask the candidate for clarification only if a required input cannot reasonably be resolved from the supplied material.

## 11.6 Research graph flow

```mermaid
flowchart TD
    START([Start company/JD preparation]) --> INPUT[Load company, role and JD context]
    INPUT --> JD{JD supplied?}
    JD -->|Yes| EXTRACT[Load processed JD and extract requirements]
    JD -->|No| ROLE[Use role/company objective as supplied]
    EXTRACT --> RESEARCH[Gather relevant public research]
    ROLE --> RESEARCH
    RESEARCH --> SOURCES[Normalize source metadata and provenance]
    SOURCES --> VERIFY[Validate relevance and distinguish source types]
    VERIFY --> COMP[Map requirements to competencies]
    COMP --> BRIEF[Add source references and limitations to brief]
    BRIEF --> END([Continue to brief validation])
```

## 11.7 Untrusted content and prompt injection

A JD or web page may contain hostile instructions. Treat all retrieved content as untrusted data.

- Do not follow instructions embedded in JD or web page text.
- Do not reveal system prompts or internal policies.
- Do not allow external content to add tools or change graph permissions.
- Do not treat a source's claims as verified just because the model repeats them.
- Maintain clear source references.
- Validate model outputs before saving.
- Record suspicious source content in security telemetry when relevant.

---

# 12. Track Creator Agent — LangGraph design

## 12.1 Agent purpose

The Track Creator Agent creates or refreshes a preparation track from a topic, role, company and/or JD.

Inputs:

- Candidate context snapshot.
- Selected objective and track type.
- Selected topics.
- JD content/reference.
- Company and role context.
- Previous track context when refreshing.

Outputs:

- Structured preparation plan.
- Competency coverage.
- Research references where relevant.
- Versioned Interview Brief.

## 12.2 Graph invocation conditions

Invoke the graph when:

- A new topic-based track is created.
- A new role-based track is created.
- A new company/JD-based track is created.
- A material refresh is requested.

Do not invoke the full graph when:

- A candidate starts another session in an existing valid track.
- A candidate views a track.
- A candidate updates unrelated profile information.
- A session-specific setting changes without affecting the preparation objective.

If a candidate profile change is relevant, mark the track as potentially needing refresh. Do not silently regenerate or mutate its historical brief.

## 12.3 Proposed graph nodes

| Node | Responsibility |
|---|---|
| `validate_track_request` | Validate track type, required inputs and refresh/create mode |
| `load_existing_track_context` | Load prior configuration and current brief when refreshing |
| `load_candidate_context` | Retrieve selected candidate profile snapshot |
| `analyze_preparation_objective` | Interpret topic, role or company/JD objective |
| `load_job_description` | Load processed JD text/reference when supplied |
| `extract_jd_requirements` | Extract required/preferred skills and responsibilities |
| `research_company_role` | Request relevant public research where applicable |
| `normalize_research_sources` | Normalize metadata and provenance |
| `build_competency_map` | Create competency IDs, topics, priority and source labels |
| `build_interview_blueprint` | Establish sections, coverage and time allocation |
| `build_preparation_plan` | Generate initial learning priorities and practice areas |
| `compose_interview_brief` | Compose the structured brief |
| `validate_brief` | Check schema, references, coverage and constraints |
| `persist_preparation_artifacts` | Request backend save operations |
| `mark_track_ready` | Request backend readiness transition after persistence |
| `handle_preparation_error` | Retry/return safe errors |

The graph may route around JD or research nodes for topic-based and role-based tracks.

## 12.4 LangGraph flow

```mermaid
flowchart TD
    START([START]) --> VALIDATE[Validate track request]
    VALIDATE --> REFRESH{New track or refresh?}
    REFRESH -->|Refresh| EXISTING[Load previous track context]
    REFRESH -->|New| PROFILE[Load candidate context]
    EXISTING --> PROFILE
    PROFILE --> TYPE{Track type?}

    TYPE -->|TOPIC| TOPIC[Analyze topic and selected subtopics]
    TYPE -->|ROLE| ROLE[Analyze target role]
    TYPE -->|COMPANY_JD| COMPANY[Load company and JD context]

    COMPANY --> HASJD{JD available?}
    HASJD -->|Yes| EXTRACT[Extract JD requirements]
    HASJD -->|No| RESEARCH[Research relevant role/company]
    EXTRACT --> RESEARCH

    TOPIC --> COMP[Build competency map]
    ROLE --> COMP
    RESEARCH --> SOURCES[Normalize source references]
    SOURCES --> COMP

    COMP --> BLUEPRINT[Build interview blueprint]
    BLUEPRINT --> PLAN[Build preparation plan]
    PLAN --> BRIEF[Compose Interview Brief]
    BRIEF --> SCHEMA{Brief valid?}
    SCHEMA -->|No| REPAIR[Bounded correction]
    REPAIR --> SCHEMA
    SCHEMA -->|Yes| SAVE[Persist versioned artifacts]
    SAVE --> READY[Mark track ready via backend]
    READY --> END([END])
```

## 12.5 Conditional routing

| Condition | Route |
|---|---|
| Invalid or incomplete track request | Stop and return validation errors |
| New track | Create initial track preparation version |
| Material refresh | Load prior track/brief context and produce a new version |
| Topic-based | Skip company research/JD extraction unless explicitly supplied and relevant |
| Role-based without JD | Use role objective and clearly labeled general role expectations |
| Role-based with JD | Extract supplied JD requirements and distinguish them from general expectations |
| Company/JD-based with JD | Extract JD, conduct relevant public research and record provenance |
| Company/role provided without JD | Build from supplied company/role plus public sources; state limitations |
| Research unavailable | Continue only if the objective can still be prepared; explicitly record missing research |
| Brief schema invalid | Bounded repair/validation; do not set track READY |
| Persistence fails | Retry idempotently; do not advance current version pointer prematurely |
| Existing valid track session start | Do not invoke Track Creator |

## 12.6 Proposed LangGraph state

```python
from typing import TypedDict, Literal, NotRequired, Any

TrackType = Literal["TOPIC", "ROLE", "COMPANY_JD"]
PreparationOperation = Literal["CREATE", "REFRESH"]

class TrackCreatorState(TypedDict):
    # Trusted backend execution context
    user_id: str
    correlation_id: str
    graph_version: str
    operation: PreparationOperation

    # Track identity/configuration
    track_id: NotRequired[str]
    track_type: TrackType
    track_request: dict[str, Any]
    track_version_id: NotRequired[str]
    previous_brief_version_id: NotRequired[str]

    # Input references
    profile_version_id: str
    candidate_context: dict[str, Any]
    job_description_document_id: NotRequired[str]
    job_description_text: NotRequired[str]
    company_context: NotRequired[dict[str, Any]]
    previous_track_context: NotRequired[dict[str, Any]]

    # Preparation intermediates
    extracted_requirements: NotRequired[list[dict[str, Any]]]
    research_sources: NotRequired[list[dict[str, Any]]]
    competency_map: NotRequired[list[dict[str, Any]]]
    interview_blueprint: NotRequired[dict[str, Any]]
    preparation_plan: NotRequired[dict[str, Any]]

    # Outputs
    interview_brief: NotRequired[dict[str, Any]]
    validation_errors: NotRequired[list[str]]
    saved_artifact_references: NotRequired[dict[str, Any]]

    # Execution
    retry_count: int
    error_code: NotRequired[str]
    error_message_safe: NotRequired[str]
```

### State rules

- `user_id` is inserted by trusted backend context, not generated by the model.
- Do not include storage credentials, provider keys or unrestricted network permissions.
- Keep graph state bounded; use document IDs and source references instead of copying large files.
- Do not store the entire candidate profile if only selected fields are relevant.
- Do not let the graph create arbitrary database IDs or set track ownership.
- Use version IDs to keep refreshes and historical briefs separate.
- Never move a track to `READY` from inside an unvalidated model response.

## 12.7 Graph invocation and checkpointing

- Use a stable graph `thread_id` tied to the preparation job/operation.
- A new track creation and a later refresh should have distinct execution identifiers.
- Use a checkpointer only for graph execution continuity and recovery.
- PostgreSQL remains the authoritative source for track and job lifecycle.
- The backend should be able to resume/retry a job without creating duplicate brief versions.
- Persist graph version and correlation ID in job metadata.
- Do not use graph checkpoint state as authorization.
- Coordinate checkpointer storage and retention with Member 1.

---

# 13. Agent Tool Layer contracts

The Track Creator uses only the HLD-approved tools:

- `get_candidate_context`
- `create_preparation_track`
- `get_job_description`
- `save_research_sources`
- `save_interview_brief`
- `get_previous_track_context`
- `mark_track_ready`

Each tool is executed through Member 1's Agent Tool Layer. No direct SQL, MongoDB or object-storage client is exposed to the graph.

## 13.1 `get_candidate_context`

Purpose: Retrieve the relevant profile context for the authenticated candidate.

Input:

```json
{
  "track_type": "ROLE",
  "target_role": "Backend Engineer Intern",
  "selected_topics": ["Python", "Databases", "APIs"],
  "profile_version_id": "profile-version-uuid"
}
```

Output:

```json
{
  "profile_version_id": "profile-version-uuid",
  "candidate_context": {
    "education": [],
    "relevant_skills": [],
    "relevant_projects": [],
    "relevant_experience": []
  }
}
```

Authorization: backend verifies the profile version belongs to the authenticated user.

## 13.2 `create_preparation_track`

Purpose: Create or initialize track metadata through the Track Service.

Input:

```json
{
  "track_type": "TOPIC",
  "name": "DBMS Preparation",
  "objective": "PRACTICE",
  "validated_config": {
    "subject": "DBMS",
    "selected_topics": ["Normalization", "Indexing"]
  },
  "request_id": "idempotency-key"
}
```

Output:

```json
{
  "track_id": "track-uuid",
  "track_status": "PREPARING",
  "track_version_id": "track-version-uuid"
}
```

The backend assigns the track ID, owner and lifecycle status.

## 13.3 `get_job_description`

Purpose: Retrieve a JD supplied through text or processed document reference.

Input:

```json
{
  "document_id": "document-uuid"
}
```

Output:

```json
{
  "document_id": "document-uuid",
  "processing_status": "SUCCEEDED",
  "extracted_text": "Validated extracted job description text",
  "source_metadata": {
    "filename": "job-description.pdf",
    "extraction_version": "parser-version"
  }
}
```

If the JD is supplied as raw text, the backend validates and scopes the text to the authenticated track request.

## 13.4 `save_research_sources`

Purpose: Persist normalized research references and provenance.

Input:

```json
{
  "track_id": "track-uuid",
  "sources": [
    {
      "url": "https://example.com/careers/role",
      "title": "Example Role Information",
      "publisher": "Example Company",
      "source_type": "OFFICIAL_ROLE_PAGE",
      "published_at": null,
      "retrieved_at": "2026-11-02T12:00:00Z",
      "relevance_note": "Official role responsibilities"
    }
  ]
}
```

Output:

```json
{
  "saved_source_ids": ["source-uuid"],
  "count": 1
}
```

The backend validates URL format and track ownership. Do not treat arbitrary URLs as trusted instructions.

## 13.5 `save_interview_brief`

Purpose: Validate and persist a versioned Interview Brief.

Input:

```json
{
  "track_id": "track-uuid",
  "track_version_id": "track-version-uuid",
  "source_profile_version_id": "profile-version-uuid",
  "brief_schema_version": "1.0",
  "brief": {}
}
```

Output:

```json
{
  "brief_version_id": "brief-version-uuid",
  "version_number": 1,
  "validation_status": "VALIDATED",
  "status": "SAVED"
}
```

The backend validates schema, version references, ownership, competency references, research source references and required fields before saving.

## 13.6 `get_previous_track_context`

Purpose: Retrieve previous preparation data for a material refresh.

Input:

```json
{
  "track_id": "track-uuid",
  "include_current_brief": true,
  "include_research_sources": true,
  "include_preparation_plan": true
}
```

Output:

```json
{
  "track_id": "track-uuid",
  "track_version_id": "track-version-uuid",
  "current_brief_version_id": "brief-version-uuid",
  "track_config": {},
  "current_brief_summary": {},
  "research_sources": [],
  "preparation_plan": {}
}
```

## 13.7 `mark_track_ready`

Purpose: Request the backend Track Service to finalize readiness after all required artifacts are durably saved and validated.

Input:

```json
{
  "track_id": "track-uuid",
  "track_version_id": "track-version-uuid",
  "brief_version_id": "brief-version-uuid",
  "plan_version_id": "plan-version-uuid"
}
```

Output:

```json
{
  "track_id": "track-uuid",
  "status": "READY",
  "current_brief_version_id": "brief-version-uuid"
}
```

The backend verifies all referenced artifacts and state preconditions. The agent cannot independently write `READY`.

---

# 14. Track APIs

These are proposed REST endpoints. Final prefixes, response envelope and pagination must follow Member 1's common API standards.

## 14.1 Endpoint summary

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/tracks` | Create a topic/role/company-JD track |
| `GET` | `/api/v1/tracks` | List authenticated user's tracks |
| `GET` | `/api/v1/tracks/{track_id}` | Get one track |
| `PATCH` | `/api/v1/tracks/{track_id}` | Update permitted metadata/preferences |
| `POST` | `/api/v1/tracks/{track_id}/prepare` | Start or retry initial preparation |
| `POST` | `/api/v1/tracks/{track_id}/refresh` | Request material refresh |
| `GET` | `/api/v1/tracks/{track_id}/status` | Get preparation/lifecycle status |
| `GET` | `/api/v1/tracks/{track_id}/brief` | Get current Interview Brief |
| `GET` | `/api/v1/tracks/{track_id}/brief/versions` | List brief versions |
| `GET` | `/api/v1/tracks/{track_id}/brief/versions/{version_id}` | Retrieve a specific historical brief |
| `GET` | `/api/v1/tracks/{track_id}/preparation-plan` | Get current preparation plan |
| `POST` | `/api/v1/tracks/{track_id}/archive` | Archive track |
| `POST` | `/api/v1/tracks/{track_id}/resume` | Resume a paused track |

## 14.2 Create track

`POST /api/v1/tracks`

Header:

```text
Idempotency-Key: <unique-client-generated-value>
```

Request: one of the validated topic, role or company/JD schemas from Section 7.

Accepted response:

```json
{
  "data": {
    "track_id": "track-uuid",
    "track_type": "TOPIC",
    "status": "PREPARING",
    "preparation_job_id": "job-uuid"
  },
  "meta": {
    "correlation_id": "correlation-uuid"
  }
}
```

Use `202 Accepted` if preparation continues asynchronously. Use `201 Created` for the durable track resource if the API creates it synchronously and separately reports background preparation. The team must settle on one consistent response pattern.

## 14.3 Refresh track

`POST /api/v1/tracks/{track_id}/refresh`

Request:

```json
{
  "reason": "JOB_DESCRIPTION_CHANGED",
  "changes": {
    "job_description_document_id": "new-document-uuid"
  },
  "expected_track_version": 2
}
```

Response:

```json
{
  "data": {
    "track_id": "track-uuid",
    "status": "PREPARING",
    "preparation_job_id": "job-uuid",
    "previous_brief_version_id": "brief-v2-uuid"
  },
  "meta": {
    "correlation_id": "correlation-uuid"
  }
}
```

The previous brief remains preserved.

## 14.4 Get current brief

`GET /api/v1/tracks/{track_id}/brief`

Response:

```json
{
  "data": {
    "track_id": "track-uuid",
    "brief_version_id": "brief-version-uuid",
    "brief_version_number": 2,
    "brief": {}
  },
  "meta": {
    "correlation_id": "correlation-uuid"
  }
}
```

## 14.5 Track status response

```json
{
  "data": {
    "track_id": "track-uuid",
    "status": "PREPARING",
    "current_brief_version_id": "brief-v1-uuid",
    "preparation_job": {
      "job_id": "job-uuid",
      "status": "PROCESSING"
    },
    "refresh_required": false,
    "last_error_code": null
  },
  "meta": {
    "correlation_id": "correlation-uuid"
  }
}
```

## 14.6 Common error codes

| Code | Meaning | Retryable |
|---|---|---|
| `TRACK_NOT_FOUND` | Track unavailable/not found | No |
| `TRACK_NOT_OWNED` | Owner check failed | No; return safe not-found as policy requires |
| `TRACK_STATE_CONFLICT` | Invalid lifecycle transition | No |
| `INVALID_TRACK_TYPE` | Unsupported type | No |
| `INVALID_TRACK_CONFIGURATION` | Missing/inconsistent path fields | No |
| `JD_NOT_READY` | JD processing incomplete | Usually |
| `PROFILE_CONTEXT_UNAVAILABLE` | Candidate snapshot unavailable | Depends |
| `BRIEF_VALIDATION_FAILED` | Brief failed schema/reference checks | Bounded retry or correction |
| `RESEARCH_UNAVAILABLE` | Research dependency unavailable | Depends; can proceed only if policy allows |
| `PREPARATION_JOB_FAILED` | Job failed | Retry if transient |
| `VERSION_CONFLICT` | Stale expected version | No; reload |
| `IDEMPOTENCY_CONFLICT` | Same key used with different payload | No |

---

# 15. Track memory and question-history integration

## 15.1 Track memory ownership

The HLD requires every track to maintain:

- Topics assessed and not yet assessed.
- Competencies demonstrated, partially demonstrated and weakly demonstrated.
- Previous session summaries.
- Question history and fingerprints.
- Current learning priorities.
- Current Interview Brief version.

Member 2 defines how a new track's memory/context is initialized and what data contract is provided to the Interviewer. Member 4 owns assessment-driven updates after feedback. Member 3 consumes that context during an interview.

## 15.2 Initial memory record

Proposed logical MongoDB document in `track_memories`:

```json
{
  "_id": "track-memory-uuid",
  "user_id": "user-uuid",
  "track_id": "track-uuid",
  "current_brief_version_id": "brief-version-uuid",
  "assessed_topics": [],
  "not_assessed_topics": [],
  "competency_evidence_summary": [],
  "session_summaries": [],
  "learning_priorities": [],
  "created_at": "2026-11-02T12:00:00Z",
  "updated_at": "2026-11-02T12:00:00Z"
}
```

Question history is maintained in a separate shared collection, not as an unbounded array in this document.

## 15.3 Initial question history

At track creation, the collection may start empty but should exist or be lazily initialized using an idempotent operation.

Proposed `track_question_history` record fields:

- `user_id`
- `track_id`
- `session_id`
- `turn_id`
- `question_fingerprint`
- `normalized_question`
- `competency_id`
- `topic`
- `question_type`
- `mode`
- `asked_at`
- `revisit_reason`

Member 4's memory/history update workflow records asked questions after session completion or through the agreed turn service. Member 3 reads recent question history through the approved tool.

## 15.4 Context package for Member 3

Track Service should be able to supply this logical package:

```json
{
  "track": {
    "track_id": "track-uuid",
    "track_type": "ROLE",
    "status": "READY"
  },
  "interview_brief": {
    "brief_version_id": "brief-version-uuid",
    "competencies": [],
    "interview_blueprint": {},
    "evaluation_rubric": {}
  },
  "track_memory": {
    "assessed_topics": [],
    "not_assessed_topics": [],
    "learning_priorities": [],
    "recent_session_summaries": []
  },
  "question_history": {
    "recent_questions": [],
    "question_fingerprints": []
  }
}
```

The backend constructs the actual active-session context with the profile snapshot, mode and session policy. Do not expose a new-session graph with an oversized full track history.

---

# 16. Asynchronous preparation and research jobs

Some preparation operations may be sufficiently long-running to run asynchronously. The Track Service should decide which paths run synchronously and which become jobs. The LLM calls themselves do not require every step to be an independent NATS job.

## 16.1 Candidate job categories

- `TRACK_CREATION`
- `TRACK_REFRESH`
- `COMPANY_RESEARCH`
- `JD_EXTRACTION` (usually initiated by the document pipeline owned by Member 1)

## 16.2 Event example

Proposed subject:

```text
track.preparation.requested
```

Event:

```json
{
  "event_id": "event-uuid",
  "event_type": "track.preparation.requested",
  "event_version": 1,
  "job_id": "backend-generated-job-uuid",
  "correlation_id": "correlation-uuid",
  "occurred_at": "2026-11-02T12:00:00Z",
  "payload": {
    "track_id": "track-uuid",
    "track_version_id": "track-version-uuid",
    "operation": "CREATE"
  }
}
```

The event contains identifiers and compact metadata, not full profile/JD content. Worker validates `job_id` and retrieves scoped data through backend services.

## 16.3 Reliability rules

- Use durable JetStream consumers.
- Use explicit acknowledgments.
- Assume duplicate delivery.
- Validate job against PostgreSQL.
- Use `job_id` and track version for idempotency.
- Bounded retries and backoff.
- Dead-letter after retry exhaustion.
- Do not mark track `READY` before required artifacts are durably saved.
- Reconcile job and track state after partial failures.
- Do not create a second track/brief due to duplicate delivery.

Coordinate stream configuration, publisher/outbox and worker conventions with Member 1.

---

# 17. Security, privacy and guardrails

## 17.1 Authorization

- Every track operation is scoped to the authenticated user.
- Candidate context retrieval verifies profile ownership.
- JD document references verify document ownership.
- Research source writes verify track ownership.
- Brief persistence verifies track/version ownership.
- Historical brief retrieval verifies track ownership.
- Tool calls use trusted backend context.
- The Track Creator cannot assign track ownership or change user IDs.

## 17.2 Untrusted inputs

Treat as data, not instructions:

- Uploaded resumes.
- Uploaded JDs.
- Candidate-entered role descriptions.
- External company pages.
- Public engineering/blog pages.
- Research snippets and retrieved source text.

## 17.3 Guardrails

- Ignore instructions embedded in a JD or webpage that ask the agent to reveal prompts, use tools or change its role.
- Do not claim access to private hiring information.
- Do not fabricate sources, dates, quotes, job requirements or company practices.
- Distinguish JD-required skills from general role expectations and model inferences.
- Do not invent candidate achievements or skill levels.
- Validate every structured output.
- Restrict tools using the role-specific allowlist.
- Do not let the model create arbitrary URLs or access arbitrary storage keys without backend validation.
- Record suspicious content separately from competency and assessment data.

## 17.4 Privacy

- Only use profile fields relevant to the track.
- Do not copy the entire Candidate Context Vault into the Interview Brief.
- Keep private source documents in object storage.
- Do not include personal information in research requests unless necessary and authorized.
- Do not log full prompts/JDs by default.
- Define document, source and preparation-artifact retention policies.

---

# 18. Observability

## 18.1 Correlation identifiers

Propagate:

- `user_id`
- `track_id`
- `track_version_id`
- `brief_version_id`
- `plan_version_id`
- `job_id`
- `correlation_id`
- `graph_run_id`
- `graph_version`
- `llm_call_id`

## 18.2 Metrics

Track:

### Track lifecycle
- Track creation count by type.
- Track preparation success/failure.
- Time to ready.
- Refresh count and reason.
- Number of tracks in `NEEDS_REFRESH`.
- Track creation duplicate/idempotency conflicts.

### Preparation quality/validation
- Brief schema validation failure rate.
- Missing competency mapping rate.
- Research source availability.
- JD extraction validation failures.
- Preparation job retries/dead-letter count.

### LLM usage
- Calls per Track Creator graph.
- Tokens and estimated cost per preparation.
- Latency by operation/model alias.
- Provider timeout/fallback rate.
- Cost per track and per brief version.

Avoid logging raw candidate profile data, JD content or full prompts in metrics.

---

# 19. Testing strategy

## 19.1 Track service unit tests

- Create topic track.
- Create role track.
- Create company/JD track.
- Reject wrong type-specific payload.
- Reject a document belonging to another user.
- List only current user's tracks.
- Update allowed metadata.
- Reject invalid state transition.
- Archive without deleting historical sessions.
- Idempotent creation request.
- Version conflict handling.

## 19.2 Track Creator LangGraph tests

- Topic flow skips unnecessary company research.
- Role flow produces general role expectations labeled as such.
- Company/JD flow extracts JD requirements and includes public research references where available.
- No-JD company flow records assumptions/limitations.
- Refresh flow loads prior context.
- New track flow does not require previous context.
- Missing profile context produces a controlled error/limited brief rather than invented candidate facts.
- Invalid graph output fails schema validation.
- Research unavailable follows approved fallback/limitation behavior.
- Graph cannot call tools outside its allowlist.
- Prompt injection in JD/web content does not change graph instructions.
- Persistence failure does not mark track READY.
- Duplicate graph/job run does not create duplicate brief versions.

## 19.3 Versioning tests

- New track creates initial track/brief/plan versions.
- Material refresh creates a new version.
- Prior brief remains retrievable.
- Old session retains old brief version reference.
- Profile update marks track potentially stale but does not rewrite brief.
- Brief pointer advances only after successful validation and persistence.
- Failed refresh retains prior valid brief.

## 19.4 Integration tests with other members

- Profile version retrieval with Member 1.
- JD document processing and storage key resolution with Member 1.
- Common graph/tool/LLM Gateway contract with Member 1.
- Interviewer consumes brief and track context with Member 3.
- Feedback Agent consumes competency/rubric IDs with Member 4.
- Memory update from Member 4 preserves current brief/version references.
- Strict/Guided policy remains owned by backend/Member 4; Track Creator does not set it.

## 19.5 Acceptance criteria

Member 2's module is ready for implementation review when:

- All three preparation paths are supported in the design.
- Track ownership and isolation are enforced.
- Track lifecycle matches the HLD.
- Track Creator graph has explicit state, nodes and conditional routes.
- Interview Brief is structured, validated and versioned.
- Preparation Plan references the correct competencies.
- JD/company research retains source provenance and limitations.
- New session creation reuses a valid track instead of recreating it.
- Material refresh preserves all old versions.
- Member 3 and Member 4 have stable input contracts.
- All graph writes pass through the backend Tool Layer.

---

# 20. Suggested implementation sequence

| Step | Work | Deliverable |
|---|---|---|
| 1 | Agree common IDs, API conventions and tool contract with Member 1 | Shared interface |
| 2 | Define track types, creation schemas and lifecycle | Track domain schema |
| 3 | Implement Track CRUD and ownership | Track APIs |
| 4 | Define track version and refresh model | Versioned metadata |
| 5 | Define Interview Brief JSON schema with Members 3 and 4 | Shared brief contract |
| 6 | Define competency and preparation plan schema | Preparation artifacts |
| 7 | Implement Candidate Context retrieval integration | Bounded context package |
| 8 | Implement JD/document processing integration | JD input flow |
| 9 | Implement research source contract | Provenance records |
| 10 | Build Track Creator LangGraph | Graph state/nodes/edges |
| 11 | Implement validation and persistence tools | Validated artifact writes |
| 12 | Implement NATS preparation jobs if asynchronous execution is required | Worker integration |
| 13 | Implement initial track memory/question-history setup | Track context foundation |
| 14 | Integrate with Member 3 and Member 4 | End-to-end contracts |
| 15 | Add observability, retries and tests | Implementation readiness |

---

# 21. Repository structure for Member 2

```text
LLD/
└── 02_Track_Management/
    ├── README.md
    ├── module_overview.md
    ├── track_types_and_inputs.md
    ├── track_lifecycle.md
    ├── track_management_apis.md
    ├── track_database_design.md
    ├── track_versioning_refresh.md
    ├── track_creator_agent_langgraph.md
    ├── candidate_context_selection.md
    ├── company_jd_research.md
    ├── competency_mapping.md
    ├── preparation_plan.md
    ├── interview_brief_schema.md
    ├── track_memory_initialization.md
    ├── tool_contracts.md
    ├── security_guardrails.md
    ├── observability.md
    ├── testing_strategy.md
    ├── diagrams/
    │   ├── track_create.mmd
    │   ├── track_refresh.mmd
    │   ├── track_state.mmd
    │   ├── track_creator_graph.mmd
    │   ├── research_workflow.mmd
    │   └── track_context_handoff.mmd
    └── schemas/
        ├── track_create.schema.json
        ├── interview_brief.schema.json
        ├── preparation_plan.schema.json
        ├── research_source.schema.json
        └── track_creator_state.schema.json
```

---

# 22. Cross-member integration checklist

## With Member 1 — Platform and Data Foundation

- [ ] Use common authentication context and internal user IDs.
- [ ] Use shared PostgreSQL/MongoDB conventions.
- [ ] Use the common Agent Tool Layer.
- [ ] Use the shared LangGraph invocation/checkpoint conventions.
- [ ] Use the InterviewCopilot LLM Gateway and LiteLLM alias routing.
- [ ] Use the shared NATS job/event envelope.
- [ ] Use Member 1's document processing and object-storage references.
- [ ] Follow shared API/error and correlation standards.

## With Member 3 — Interview Engine

- [ ] Interview Brief schema is finalized and versioned.
- [ ] Track context package is agreed.
- [ ] Competency IDs are stable.
- [ ] Interview blueprint and time/coverage contract is agreed.
- [ ] Current brief pointer can be retrieved safely.
- [ ] Session stores exact brief/profile version references.
- [ ] Track refresh never changes an active session's context.
- [ ] New session in a valid track does not trigger Track Creator.

## With Member 4 — Assessment and Feedback

- [ ] Competency definitions map to assessment schema.
- [ ] Rubric references in Interview Brief are stable.
- [ ] Evidence criteria are sufficiently clear for assessment.
- [ ] `NOT_ASSESSED` is represented in the competency map/coverage model.
- [ ] Track memory update contract is agreed.
- [ ] Learning-priority data can be updated after feedback without rewriting the original preparation plan version.
- [ ] Historical report remains linked to original brief version.

---

# 23. Open decisions register

| Decision | Proposed direction | Status |
|---|---|---|
| Exact track config schema | Typed common fields plus validated type-specific configuration | Open |
| Track duplicate detection | Use objective identity fields and candidate confirmation; avoid accidental merge | Open |
| Track archive behavior with active session | Coordinate with Member 3; likely disallow archive while active session exists | Open |
| Topic taxonomy/domain packs | Begin with extensible domain-neutral competency schema | Open |
| Role expectation source | Label as general role expectations unless tied to official JD/source | Open |
| Company research provider | Use a provider-agnostic research tool interface | Open |
| Research freshness | Define policy by source type and opportunity timing | Open |
| JD extraction/parser | Member 1 owns parser selection; Member 2 validates extracted requirements | Open |
| Interview Brief schema version | Versioned JSON Schema, coordinated with Members 3 and 4 | Open |
| Refresh trigger thresholds | Define what is considered a material profile/JD/topic change | Open |
| Preparation plan editing | Decide whether candidate can edit generated plan before session | Open |
| Track memory initialization | MongoDB document in shared `track_memories` collection | Proposed |
| NATS for track preparation | Use only if operation is async/long-running; don't split every graph node into a job | Proposed |
| Graph checkpoint store | Follow Member 1's selected LangGraph checkpoint implementation | Open |
| Brief approval UX | Decide which preparation artifacts the candidate can review before starting | Open |

---

# 24. Final design summary

Member 2 owns the workflow that turns a candidate's preparation objective into a structured and reusable Preparation Track.

The student can choose topic-based, role-based or company/JD-based preparation. The backend validates the input, creates the track and supplies a bounded candidate context snapshot. The Track Creator Agent runs as a LangGraph workflow. Depending on the track type, it analyzes the objective, extracts JD requirements, gathers relevant public research, maps competencies, builds an interview blueprint and preparation plan, and composes a versioned Interview Brief.

The graph returns structured outputs through the Agent Tool Layer. Backend services validate the schemas and references, persist the preparation artifacts in PostgreSQL, and transition the track to `READY` only after durable persistence succeeds. Research source metadata is retained so the brief can distinguish official employer information, third-party sources, general role expectations and model inferences.

A material change creates a new preparation/brief version. Historical sessions and reports retain their original profile and Interview Brief references. A normal new interview session in a valid track reuses the existing brief and track memory; it does not rerun the Track Creator.

Member 2 initializes the track's context and defines the contract consumed by the Interviewer. Assessment-driven memory and question-history updates are coordinated with Member 4. The Track Creator does not own Strict/Guided eligibility.

**The outcome for Member 2 is an implementation-ready Track Management and Track Creator design: independent tracks, versioned preparation artifacts, traceable research, stable competency contracts, and a reusable LangGraph workflow that integrates with Members 1, 3 and 4.**
