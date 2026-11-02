# InterviewCopilot

## Product Overview, User Journey, Feature Definition, and Student Improvement Cycle

**Document type:** Product vision and experience definition
**Version:** 0.1 — Working product specification
**Status:** Product direction consolidated; detailed agent architecture and implementation design intentionally deferred
**Product name:** InterviewCopilot
**Product category:** AI-powered interview preparation, simulation, assessment, and coaching platform
**Primary audience:** University students and fresh graduates across academic disciplines
**Product philosophy:** Understand the candidate, conduct a realistic interview, identify genuine gaps, and help the candidate improve.

> **Working tagline:** Know your story. Face your interview. Close your gaps.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Context and the Need](#2-product-context-and-the-need)
3. [Product Vision, Mission, and Positioning](#3-product-vision-mission-and-positioning)
4. [Target Users and Supported Preparation Domains](#4-target-users-and-supported-preparation-domains)
5. [Core Product Concepts and Terminology](#5-core-product-concepts-and-terminology)
6. [The Candidate Context Vault](#6-the-candidate-context-vault)
7. [Preparation Paths and Preparation Tracks](#7-preparation-paths-and-preparation-tracks)
8. [End-to-End Student User Journey](#8-end-to-end-student-user-journey)
9. [Interview Preparation and the Interview Brief](#9-interview-preparation-and-the-interview-brief)
10. [The Interview Experience](#10-the-interview-experience)
11. [Strict Interview and Guided Interview](#11-strict-interview-and-guided-interview)
12. [Assessment and Target-Role Readiness](#12-assessment-and-target-role-readiness)
13. [The Student Improvement Cycle](#13-the-student-improvement-cycle)
14. [Multiple Tracks, Companies, Subjects, and Sessions](#14-multiple-tracks-companies-subjects-and-sessions)
15. [Worked Example: One Student Using InterviewCopilot](#15-worked-example-one-student-using-interviewcopilot)
16. [Feature Catalogue](#16-feature-catalogue)
17. [Suggested Product Screens and Navigation](#17-suggested-product-screens-and-navigation)
18. [Product Principles, Quality, Privacy, and Trust](#18-product-principles-quality-privacy-and-trust)
19. [Conceptual Data and Storage Direction](#19-conceptual-data-and-storage-direction)
20. [MVP Scope and Suggested Delivery Phases](#20-mvp-scope-and-suggested-delivery-phases)
21. [Market Context and Differentiation](#21-market-context-and-differentiation)
22. [Product Success Measures](#22-product-success-measures)
23. [Open Decisions for the Next Design Stage](#23-open-decisions-for-the-next-design-stage)
24. [Glossary](#24-glossary)
25. [Reference Links](#25-reference-links)

---

# 1. Executive Summary

InterviewCopilot is an AI-powered platform that helps students and fresh graduates prepare for interviews through personalized candidate understanding, realistic interview simulations, evidence-based assessment, and continuous improvement.

The platform is designed for students from different academic streams—not only computer science. A candidate may be preparing for Data Structures and Algorithms (DSA), system design, electronics, embedded systems, mechanical engineering, finance, business, or another subject or role. The product architecture should support different academic and professional domains through extensible domain-specific knowledge and evaluation packs.

InterviewCopilot begins by building a rich understanding of the student. A resume is an important input, but it is not the complete candidate profile. The student can explain projects, internships, research, achievements, technical decisions, responsibilities, challenges, and personal learning experiences through a conversational onboarding process. The platform structures and saves this information in a persistent **Candidate Context Vault**.

The student then creates one or more **Preparation Tracks**. A track represents a particular preparation objective, such as:

- A subject or topic, such as DSA or Digital Electronics.
- A target role, such as Backend Engineer Intern or Data Analyst.
- A company-specific opportunity, such as a Software Engineer Intern role at a named company, optionally supported by a job description (JD).

Each Preparation Track has its own interview history, preparation configuration, assessment evidence, improvement recommendations, and Strict/Guided mode eligibility. The Candidate Context Vault is shared across tracks, but the track-specific interview history and unlock rules remain separate.

Every new track begins with **Strict Interview** sessions. Strict Interview is a normal, realistic interview without hints, teaching, or answer assistance. After the student completes three Strict Interview attempts in that same track, InterviewCopilot evaluates the combined evidence. If the student is genuinely struggling and the evaluation shows insufficient performance, **Guided Interview** becomes available for that track.

Guided Interview is still an interview. It is not a separate exam, a mandatory validation assessment, or a mode that replaces normal interviewing. It gives the student optional access to hints, progressive clues, explanations, examples, and teacher-like guidance when needed. The student can continue interviewing normally, request help at a particular point, or choose Strict Interview again. Guided sessions support learning; hints used in Guided sessions must not be treated as independent evidence of unaided competency.

The product's main loop is:

**Understand the student → Define a preparation objective → Prepare the interview → Conduct the interview → Assess demonstrated performance → Help the student improve → Continue practicing.**

The purpose is not to predict whether a company will hire the student. It is to give the student a credible, transparent view of how their demonstrated abilities align with the requirements of a selected subject, role, or job opportunity—and what they can do to improve.

---

# 2. Product Context and the Need

## 2.1 The problem

Students often prepare for interviews using scattered resources: question lists, online tutorials, notes, coding platforms, peer practice, and generic AI chatbots. These resources can be useful, but they do not always create a coherent picture of the candidate or a structured preparation journey.

Common problems include:

1. **Generic preparation:** The same questions are shown to students with very different backgrounds, projects, and skill levels.
2. **Shallow resume understanding:** A resume lists keywords and short project summaries but rarely captures the student's actual contribution or depth of understanding.
3. **Limited interview practice:** Reading answers is not the same as explaining a concept under interview conditions.
4. **Weak diagnosis:** Students may know that an interview went poorly without knowing which concepts or competencies caused the difficulty.
5. **Unstructured improvement:** Feedback is often disconnected from a practical follow-up plan.
6. **No continuity:** A new preparation session may ignore the student's previous performance and learning history.
7. **Different discipline requirements:** Students from different academic streams require different subject knowledge, question styles, and evaluation criteria.
8. **Company and role uncertainty:** A candidate may not know which skills are relevant to a particular job description or what public information is credible when preparing for a company-specific interview.

## 2.2 The opportunity

InterviewCopilot brings candidate context, preparation objectives, interview practice, assessment, and learning into one continuing experience.

The platform should help answer five questions for every student:

- **Who am I as a candidate?** What have I studied, built, researched, and contributed to?
- **What am I preparing for?** Which subject, role, company, or job opportunity matters now?
- **What might an interview examine?** Which competencies are relevant, and why?
- **How did I actually perform?** What did I demonstrate during the interview, and what evidence supports the assessment?
- **What should I do next?** Which concepts or skills should I improve, and how can I practice them?

## 2.3 The product's central idea

InterviewCopilot should not merely interview a resume. It should interview the person behind the resume.

A resume statement such as “Built an AI-powered recommendation system” is only a starting point. The platform should be able to discover and use the student's actual context:

- What problem was being solved?
- What was the student's personal responsibility?
- Which algorithms or methods were implemented?
- What alternatives were considered?
- What did not work, and why?
- How was the output evaluated?
- What were the limitations?
- What would the student improve now?

That depth allows the interviewer to ask meaningful, candidate-specific follow-up questions rather than relying only on generic questions.

---

# 3. Product Vision, Mission, and Positioning

## 3.1 Product vision

To become a trusted AI interview preparation companion that helps students understand their strengths, face realistic interviews, improve their weaknesses, and build confidence through evidence-based practice.

## 3.2 Product mission

To make high-quality, personalized interview practice accessible to students across academic disciplines by combining deep candidate context, realistic interviewing, fair assessment, and supportive learning.

## 3.3 Positioning statement

**InterviewCopilot is an AI-powered interview intelligence and readiness platform for students.** It understands the student's academic and practical background, prepares interviews around a chosen subject, role, or company, conducts realistic voice or text interviews, and turns observed performance into specific improvement actions.

## 3.4 What InterviewCopilot is—and is not

InterviewCopilot is:

- A personalized interview preparation platform.
- A realistic mock-interview environment.
- A candidate-context and experience organizer.
- An evidence-based assessment and feedback tool.
- A guided practice and improvement companion.

InterviewCopilot is not:

- A guarantee of selection or employment.
- An official representative of any employer.
- An insider source for confidential company hiring information.
- A tool for fabricating resume experience or interview answers.
- A replacement for formal education or professional certification.
- A system that should judge a person's worth, personality, or protected characteristics.

---

# 4. Target Users and Supported Preparation Domains

## 4.1 Initial and long-term audience

The intended audience is university students and fresh graduates across academic disciplines. The architecture should be domain-neutral and expandable from the beginning.

The initial product should not claim deep, validated evaluation coverage for every discipline on day one. Instead, the platform should support a shared interview workflow with domain-specific knowledge packs added and validated progressively.

## 4.2 Example academic and professional domains

| Domain | Example preparation subjects |
|---|---|
| Computer Science / IT | DSA, programming, DBMS, operating systems, computer networks, system design, cybersecurity, AI/ML |
| Electronics / ECE | Digital electronics, analog electronics, VLSI, embedded systems, signals and systems, communication systems |
| Electrical | Electrical machines, power systems, control systems, power electronics |
| Mechanical | Thermodynamics, fluid mechanics, manufacturing, mechanics, machine design |
| Civil | Structural engineering, geotechnical engineering, surveying, construction management |
| Business / Commerce | Accounting, finance, marketing, business analytics, operations, management |
| Other disciplines | Domain-specific technical, professional, and behavioral preparation |

## 4.3 Shared platform, domain-specific packs

The platform should share common capabilities:

- Candidate Context Vault.
- Preparation Tracks.
- Interview configuration.
- Interview conversation and session management.
- Transcript and evidence collection.
- Assessment reporting.
- Learning recommendations.
- Progress history.

Each domain pack should contribute:

- Subject taxonomy and concepts.
- Competency definitions.
- Question categories and difficulty levels.
- Interview formats and common task types.
- Domain-specific evaluation rubrics.
- Trusted learning references and source material.
- Practical assessment tools, where needed.

This makes it possible to expand into a new discipline without redesigning the entire platform.

---

# 5. Core Product Concepts and Terminology

The following terms should be used consistently in the product, product requirements, database model, and future technical documentation.

## 5.1 Candidate Context Vault

The persistent, student-controlled collection of candidate information: academic background, skills, internships, projects, research, achievements, documents, and additional context. It is shared across the student's preparation tracks.

## 5.2 Preparation Track

A named, continuing preparation objective. A track has its own configuration, interview sessions, history, assessment evidence, recommendations, and Strict/Guided access state.

Examples:

- `TOPIC — Data Structures & Algorithms`
- `TOPIC — Digital Electronics`
- `ROLE — Backend Engineer Intern`
- `COMPANY — Northstar Technologies / Backend Engineer Intern`

The identifiers above are illustrative display labels, not prescribed database IDs.

## 5.3 Interview Session

One individual interview attempt inside a Preparation Track. A track can contain multiple sessions.

Examples:

- DSA — Strict Interview 01.
- DSA — Strict Interview 02.
- DSA — Guided Interview 01.
- Backend Engineer Intern — Strict Interview 01.

## 5.4 Interview Brief

The structured preparation artifact created before an interview. It contains the candidate context selected for the session, the preparation objective, role or company details, relevant research, interview blueprint, question strategy, coverage requirements, and evaluation rubric.

## 5.5 Domain Pack

A subject- or profession-specific knowledge and evaluation package used by the shared interview platform.

## 5.6 Assessment Report

A post-session report that explains what the candidate demonstrated, what was weak or incomplete, which areas were not assessed, and what evidence supports each conclusion.

## 5.7 Improvement Cycle

The repeatable process of reviewing feedback, practicing weak areas, returning to interviews, and observing change over time.

## 5.8 Important separation

A **Preparation Track is not the same as an Interview Session**. One track can contain many sessions. A student can also have many active tracks at the same time.

The Candidate Context Vault is shared. Track histories, attempt counters, assessment snapshots, and Guided Interview eligibility are kept separate by track.

---

# 6. The Candidate Context Vault

## 6.1 Why it matters

A resume is a concise summary, not a complete account of the candidate. Students should be able to provide deep context about their experiences in their own words.

The Candidate Context Vault should become richer as the student adds information and completes onboarding conversations. InterviewCopilot should use only relevant, permitted context for a given interview.

## 6.2 Profile sections

### A. Basic and academic profile

- Name and basic account/profile details.
- University or institution.
- Degree and academic stream.
- Specialization.
- Current year or graduation year.
- Relevant coursework.
- Academic interests and achievements.

### B. Skills and knowledge

- Programming languages.
- Tools, platforms, libraries, and frameworks.
- Technical subjects.
- Domain-specific knowledge.
- Communication, teamwork, leadership, and other professional skills.
- Self-reported familiarity level.

Self-reported skill levels are not proof of competency. Interview performance should independently establish what the student can demonstrate.

### C. Projects

Each project should be able to capture:

- Project name and objective.
- Problem being solved and intended users.
- Why the student chose the project.
- Architecture and design.
- Technologies, frameworks, and tools.
- Data or input sources, where applicable.
- The student's personal contribution.
- Implementation details and important decisions.
- Alternatives considered and trade-offs.
- Problems, bugs, and failed approaches.
- Results and how they were measured.
- Limitations and future improvements.
- Repository, demo, report, presentation, or documentation links.

### D. Internships and professional experience

Each experience should capture:

- Organization and team context.
- Role/title and duration.
- What the organization or team worked on.
- Responsibilities assigned to the student.
- What the student personally completed.
- Technologies and tools used.
- Decisions made and reasons.
- Challenges and mistakes.
- Collaboration and dependencies.
- Results and measurable outcomes, if available.
- What the student learned.
- What the student would do differently now.

### E. Research and academic work

- Research papers and publications.
- Research projects and lab work.
- Methodology and tools.
- Individual contribution.
- Findings, limitations, and future work.
- Conference, journal, or presentation details.

### F. Achievements and additional experience

- Certifications.
- Hackathons and competitions.
- Open-source contributions.
- Freelance work.
- Leadership and volunteering.
- Clubs and extracurricular activities.
- Awards and other relevant achievements.

### G. Open-ended personal context

The student should have a free-text space to explain anything relevant that does not fit another section. Examples:

- “I learned React independently by building three applications.”
- “I contributed mainly to the backend in our college project.”
- “I am comfortable with Python but still learning C++.”
- “I have not attended a formal technical interview before.”
- “I am transitioning from electronics into software engineering.”

## 6.3 Conversational profile building

Conversational onboarding is the preferred profile-building experience. It should feel like a discovery conversation, not a long form disguised as a chatbot.

A typical flow:

1. The AI welcomes the student and explains what it is trying to understand.
2. It asks about education and academic interests.
3. It asks about projects, internships, research, and other experiences.
4. It asks meaningful follow-up questions about ownership, implementation, decisions, challenges, and results.
5. It summarizes what it understood.
6. It identifies missing or ambiguous details without inventing information.
7. The student reviews, corrects, confirms, or skips the extracted information.
8. Confirmed information is saved to the Candidate Context Vault.

The student should be able to pause onboarding, skip a section, add details later, or start interview preparation with a basic profile.

## 6.4 Resume and document support

The student can upload a resume and relevant supporting materials such as project reports, presentations, research papers, or public documentation.

The platform should:

- Extract information into candidate-profile fields.
- Link extracted facts to their source document and location where feasible.
- Highlight uncertain or conflicting details for review.
- Avoid treating a technology keyword as proof of expertise.
- Allow multiple resume versions for different roles.
- Allow students to update or remove outdated information.

Students should be warned not to upload confidential employer, client, research participant, or proprietary material without permission.

## 6.5 Provenance and confidence

Important profile claims should retain their origin and status. Suggested provenance labels:

- **Candidate-entered:** Directly written or stated by the student.
- **Resume-derived:** Extracted from a resume.
- **Document-derived:** Extracted from an uploaded supporting document.
- **AI-inferred:** Suggested by the system but not confirmed.
- **Candidate-confirmed:** Reviewed and confirmed by the student.
- **Interview-demonstrated:** Supported by an observed interview response or practical task.

AI-inferred information must not silently become a fact. Candidate claims and demonstrated competency must remain distinguishable.

---

# 7. Preparation Paths and Preparation Tracks

Every new preparation objective creates or opens a Preparation Track. InterviewCopilot supports three primary entry paths.

## 7.1 Path A — Topic-based preparation

The student wants to practice a specific subject or group of topics without necessarily targeting a company.

Examples:

- Data Structures & Algorithms.
- System Design.
- DBMS.
- Digital Electronics.
- Thermodynamics.
- Financial Accounting.

Suggested inputs:

- Subject or topic.
- Selected subtopics.
- Current experience level (optional and self-reported).
- Desired difficulty.
- Interview duration.
- Interview objective: assess current knowledge, practice, revise, or simulate an interview.
- Optional interview style or role context.

Example track:

`TOPIC — Data Structures & Algorithms`

DSA sessions can cover arrays, strings, trees, graphs, dynamic programming, complexity analysis, and other selected areas. If the student starts a materially different subject, such as DBMS, it should normally be a separate track.

## 7.2 Path B — Role-based preparation

The student is preparing for a profession or job role but does not have a specific company in mind.

Examples:

- Software Engineer Intern.
- Backend Engineer.
- Data Analyst.
- Embedded Systems Engineer.
- Mechanical Design Engineer.
- Financial Analyst.

Suggested inputs:

- Target role.
- Experience level or career stage.
- Academic background.
- Optional preferred industry.
- Optional job description.
- Relevant subjects or skill areas.
- Interview duration and preferred difficulty.

The system identifies common role competencies using reliable, current role information and the inputs supplied by the student. It should make clear where it is using general role expectations rather than a specific employer's requirements.

Example track:

`ROLE — Backend Engineer Intern`

## 7.3 Path C — Company- and job-description-based preparation

This path is for a student preparing for a particular company, role, and opportunity.

Suggested inputs:

- Company name.
- Target role/title.
- Job description text or upload, if available.
- Specific expected interview stage, if known.
- Expected interview date, if known.
- Optional topics the student wants to prioritize.

Possible interview-stage choices:

- Online assessment.
- Technical screening.
- DSA/coding round.
- Project discussion.
- System design or domain-specific technical round.
- Managerial round.
- HR/behavioral round.
- Unknown or full-process simulation.

Company research should investigate relevant public information, but must not claim access to confidential interview questions or internal hiring rubrics.

Example track:

`COMPANY — Northstar Technologies / Backend Engineer Intern / JD v1`

Northstar Technologies is a fictional company name used for examples in this document.

## 7.4 Track creation and reuse rules

A track should be reused when the student is continuing the same preparation objective and the scope remains materially compatible.

Create a separate track when the student changes to a substantially different subject, role, company opportunity, or job description.

For company-specific preparation, track identity should consider:

- Company.
- Role.
- Job description or opportunity version.
- Selected interview objective/stage.

A materially changed JD or role may require a new track or an explicit new track version. The product should preserve old reports rather than rewriting historical results against new requirements.

---

# 8. End-to-End Student User Journey

## 8.1 First-time user journey

### Step 1 — Landing page and account creation

The student learns what InterviewCopilot does and creates an account.

The product should explain that it provides practice and coaching, not a hiring guarantee.

### Step 2 — Basic profile setup

The student enters essential academic and career information. They can upload a resume immediately or continue without one.

### Step 3 — Conversational profile discovery

The AI asks about the student's academic background, projects, internships, skills, achievements, research, and goals. It follows up to understand what the student actually did.

The student can skip, pause, or add details later.

### Step 4 — Review the Candidate Context Vault

The platform presents an organized summary of the information it has extracted or collected. The student can edit, confirm, remove, or mark details as uncertain.

### Step 5 — Student dashboard

The dashboard shows:

- Candidate profile completion and pending review items.
- Existing Preparation Tracks.
- Recent Interview Sessions.
- Recent feedback and recommended next actions.
- A way to create a new preparation track.

### Step 6 — Choose a preparation path

The student chooses topic-based, role-based, or company/JD-based preparation.

### Step 7 — Configure the preparation track

The student supplies the relevant subject, role, company, JD, topics, duration, difficulty, and other preferences.

### Step 8 — Prepare the interview

InterviewCopilot selects relevant candidate context, analyzes the preparation objective, performs necessary research, and prepares a structured Interview Brief.

The interface should show a clear preparation state. A one-to-two-minute preparation experience may be a useful target for common cases, but it should not be promised as a universal fixed duration. Research should be cached and reused when it remains current and relevant.

### Step 9 — Review the interview plan

The student can see the intended interview format, major competency areas, duration, and mode. The product should not reveal the actual question sequence when doing so would compromise the simulation.

### Step 10 — Conduct the interview

The student completes the interview using voice or text. The interviewer follows a planned structure and adapts follow-up questions based on the conversation.

### Step 11 — Complete the session and collect evidence

The platform saves the interview transcript, questions, responses, timestamps, selected mode, hint usage where relevant, code artifacts where supported, and session metadata.

### Step 12 — Receive assessment or learning feedback

For Strict Interview, the platform generates an evidence-based assessment. For Guided Interview, it provides a supportive learning summary and records what assistance was used.

### Step 13 — Continue the track or start another

The student can repeat the same track, follow recommended learning activities, or create a separate track for another subject, role, or company.

## 8.2 Returning user journey

A returning student should not need to repeat profile onboarding. They should be able to:

1. Open an existing Preparation Track.
2. Review its latest session and progress.
3. Start the next Strict or Guided session, depending on track eligibility.
4. Update the Candidate Context Vault when experience changes.
5. Create a new track for a different subject, role, company, or JD.

---

# 9. Interview Preparation and the Interview Brief

## 9.1 Preparation stage purpose

The preparation stage transforms candidate context and interview objectives into a structured plan that the interviewer can use consistently.

It should not rely solely on one long, unstructured generated prompt. The system should produce a structured, versioned Interview Brief that can be inspected, validated, and reused where appropriate.

## 9.2 Interview Brief contents

An Interview Brief should include:

| Section | Contents |
|---|---|
| Candidate summary | Relevant academic background, experience, projects, and skills |
| Selected candidate evidence | The profile items relevant to this specific interview |
| Preparation objective | Subject, role, company, JD, and interview stage |
| Requirements | Required and preferred competencies derived from the JD or objective |
| Company/role context | Relevant public company and role research, where applicable |
| Interview blueprint | Sections, intended coverage, order, and time allocation |
| Question strategy | Question types, difficulty range, and follow-up strategy |
| Evaluation rubric | Competencies and criteria to evaluate |
| Evidence requirements | What a sufficient answer should demonstrate |
| Interview constraints | Duration, voice/text, strict/guided mode, hint policy, and boundaries |
| Source references | URLs, source dates, reliability notes, and research confidence |

## 9.3 Company and role research

For company-specific preparation, research may include:

1. Official company career pages and job descriptions.
2. Official engineering blogs, product documentation, and technical publications.
3. Credible industry publications and relevant technical material.
4. Publicly shared candidate interview experiences, where useful and clearly labeled as anecdotal.

Each important research item should preserve its source URL, date, and confidence/reliability note. Official sources should generally carry more weight than anonymous anecdotes.

The platform must distinguish:

- **Verified information:** Supported by an official or reliable source.
- **Public anecdotal reports:** Individual experiences that may not represent the current process.
- **Inferred preparation focus:** The system's reasoned recommendation based on the role/JD and available evidence.

The system must not present a rumored question or an anecdotal interview process as a guaranteed or current company practice.

## 9.4 Research caching and freshness

The system should reuse cached research when it is relevant and sufficiently recent. It should refresh information when the company, role, JD, or research age makes the existing material unreliable.

The user should see when company research was last refreshed. If the system cannot verify a detail, it should state the uncertainty instead of inventing a confident answer.

## 9.5 Preparation time and readiness state

The preparation process may involve document extraction, profile selection, job analysis, company research, and interview-plan generation. The product should communicate progress through clear states, such as:

- Reading candidate context.
- Analyzing the preparation objective.
- Reviewing job requirements.
- Researching relevant public sources.
- Building the interview plan.
- Ready to begin.

Where possible, cached research and background preparation should reduce waiting. The product should not depend on a live external research request completing at the exact moment an interview is due to start if a suitable prepared brief is already available.

---

# 10. The Interview Experience

## 10.1 Voice and text

InterviewCopilot should support both voice and text interaction.

The two should feel like alternative ways to participate in the same interview experience, not two separate products.

Voice capabilities may include:

- Spoken interviewer questions.
- Speech-to-text transcription of candidate answers.
- Spoken responses from the AI interviewer.
- Visible transcript and conversation history.
- Ability to repeat a question.
- Ability to correct clear speech-to-text errors where appropriate.

Text capabilities may include:

- Typed answers.
- Code or structured responses where relevant.
- Visible interview transcript.
- Clear question and response navigation.

The evaluation process must account for speech recognition errors. A transcription error should not be treated as a technical misunderstanding by the candidate.

## 10.2 Hybrid interviewer behavior

The interviewer should use a **planned structure with adaptive follow-ups**.

The planned structure defines:

- What competencies must be covered.
- Which interview sections are included.
- Approximate time allocation.
- Difficulty range.
- Required evidence areas.

Adaptive behavior determines:

- Which follow-up to ask after an answer.
- Whether to probe an important claim more deeply.
- Whether to ask a simpler diagnostic question.
- Whether to increase difficulty after a strong response.
- Whether to move on to preserve coverage and time.

This avoids two undesirable extremes:

- A completely fixed questionnaire that ignores the candidate's answers.
- A completely free-form conversation that loses the interview objective and skips required competencies.

## 10.3 Example interview sequence

A 45-minute Software Engineer Intern interview might be planned as:

| Section | Planned time |
|---|---:|
| Introduction and resume discussion | 5 minutes |
| DSA and problem solving | 15 minutes |
| Technical fundamentals | 10 minutes |
| Project deep dive | 10 minutes |
| Behavioral questions | 5 minutes |

The interviewer may adjust time based on the conversation, but it should preserve essential competency coverage or report what was not assessed.

## 10.4 Interviewer behavior requirements

The interviewer should:

1. Behave professionally and naturally.
2. Ask one clear question or task at a time.
3. Use relevant candidate context without assuming unverified facts.
4. Probe important resume and profile claims.
5. Adjust follow-up depth according to the student's answer.
6. Maintain the interview objective and coverage plan.
7. Manage session time.
8. Accept “I don't know” as a valid response without forcing false confidence.
9. Avoid teaching during Strict Interview.
10. Avoid unnecessary harshness, humiliation, or personal judgment.
11. Distinguish conceptual gaps from unclear phrasing or transcription errors.
12. End the session cleanly and provide the appropriate next step.

## 10.5 Coding and practical assessment

For domains where implementation matters, verbal explanation alone is insufficient evidence of practical ability.

A later or domain-specific capability may include:

- Code editor.
- Language selection.
- Test-case execution in an isolated environment.
- Correctness and edge-case evaluation.
- Time and space complexity review.
- SQL execution against controlled datasets.
- Domain-specific calculations or practical tasks.

The assessment must distinguish a verbal explanation, a written approach, and an executable solution.

---

# 11. Strict Interview and Guided Interview

This is a defining InterviewCopilot product rule.

The two modes are not two unrelated assessment systems. They are two ways for a student to experience an interview, with different levels of assistance.

## 11.1 Strict Interview

Strict Interview is the default experience for a new Preparation Track.

It is a normal, realistic interview in which the student must answer independently.

Strict Interview rules:

- No hints or clues.
- No concept teaching during the interview.
- No suggested answers.
- No step-by-step solution assistance.
- No revealing the expected answer before the student responds.
- Natural follow-up questions are allowed.
- The interviewer can clarify or repeat a question when necessary.
- The interviewer can adapt difficulty while maintaining the planned interview coverage.
- Evaluation is based on the candidate's independent performance.

Strict does not mean rude, hostile, or artificially difficult. It means the interviewer does not assist the student in producing the answer.

## 11.2 Three-Strict-Interview unlock rule

Every new Preparation Track begins in Strict Interview mode.

After the student completes **three Strict Interview sessions within that specific track**, the system reviews the combined performance evidence.

If the student is genuinely struggling and the combined evidence indicates insufficient performance against the track's defined competencies, Guided Interview becomes available for that track.

Important rules:

1. The three-session counter is specific to one Preparation Track.
2. A weak session by itself does not automatically unlock Guided Interview.
3. The system evaluates the combined performance across the three completed Strict sessions.
4. The decision should consider competency coverage, question difficulty, quality of evidence, and consistency—not only a simple average score.
5. A session with insufficient evidence should not automatically be treated as a failed session.
6. Interrupted or abandoned sessions should not count as completed attempts unless the product later defines a specific completion rule.
7. If performance is satisfactory, Guided Interview remains locked for that track.
8. Another subject, role, or company track has its own independent three-session history and unlock decision.
9. A student cannot unlock Guided Interview for one track merely by performing poorly in another.
10. The exact performance threshold and calibration method remain product decisions to validate; they must not be presented as scientifically established before validation.

## 11.3 Guided Interview

Guided Interview becomes available only after the three-Strict-session rule has been satisfied and the track's combined assessment indicates that the student needs additional support.

Guided Interview is still a normal interview conversation. The difference is that the student can request assistance at the point where they need it.

It should feel like a supportive teacher helping a student understand a concept while continuing to practice interview-style questions.

Guided Interview capabilities:

- Optional hints.
- Progressive clues.
- Concept explanations.
- Step-by-step reasoning when requested.
- Simpler examples and analogies.
- Additional practice questions.
- Supportive follow-up questions.
- Encouraging feedback.
- The ability to continue the interview normally without requesting help.

Guided Interview should not force assistance on every question. The student decides when to request a hint or explanation.

## 11.4 Progressive hint ladder

When the student requests help, assistance should be progressive rather than immediately revealing the complete answer.

| Assistance level | Behavior |
|---|---|
| Level 1 — Gentle hint | A small conceptual nudge |
| Level 2 — Specific clue | A more direct clue about the next reasoning step |
| Level 3 — Guided reasoning | Break the problem into smaller steps and reason through them |
| Level 4 — Full explanation | Explain the concept or solution, with an example |

The student can request further help, return to answering, or continue to the next question.

## 11.5 Guided Interview is not another mandatory assessment

Guided Interview is for support and learning. It must not be turned into a second formal test or a forced validation loop.

The system may record:

- Which hints were requested.
- Which explanations were opened.
- Whether the student could continue after assistance.
- Topics that required support.
- Learning activities that may be helpful.

These observations can inform coaching recommendations. However, an answer produced after hints or teaching must not be treated as independent proof that the student could answer the same question unaided.

## 11.6 Mode availability after unlocking

Once Guided Interview is unlocked for a track:

- Guided Interview remains available for that track.
- Strict Interview remains available.
- The student may choose either mode for future sessions.
- The student is not forced to return to Strict Interview after a fixed number of Guided sessions.
- InterviewCopilot may recommend a Strict Interview when the student wants an independent check, but it must not force one.

This preserves student agency while maintaining a meaningful distinction between independent performance and assisted practice.

## 11.7 Student-facing language

Suggested labels:

- **Strict Interview:** “A realistic interview. Answer independently; hints and explanations are unavailable.”
- **Guided Interview:** “Practice with optional hints, explanations, and supportive guidance when you need it.”

The words “Strict” and “Guided” may be used internally even if user testing later suggests more approachable labels.

---

# 12. Assessment and Target-Role Readiness

## 12.1 Purpose

The assessment process should explain how the student performed in the interview and how the demonstrated competencies relate to the selected subject, role, or job description.

For company-specific preparation, the report may use the label **Target Company & Role Readiness** or **Company/Role Alignment**.

It must not claim to predict hiring outcomes or represent the company's actual hiring decision.

## 12.2 Assessment dimensions

The dimensions depend on the preparation track and its rubric. Examples include:

| Dimension | What it evaluates |
|---|---|
| Technical competency | Understanding of relevant concepts, methods, and technologies |
| Problem solving | Reasoning, approach, decomposition, and handling unfamiliar problems |
| Practical experience | Understanding of projects, internships, implementation, and ownership |
| Communication | Ability to explain concepts accurately and clearly |
| Role alignment | Evidence matching the requirements of the selected role or JD |
| Behavioral competency | Specific examples of ownership, collaboration, judgment, and learning |

A role or domain should not automatically use the same weights as another. The rubric should be configured for the selected preparation objective.

## 12.3 Evidence-backed conclusions

Every important assessment conclusion should be traceable to the interview evidence.

A useful report item should show:

- Competency assessed.
- Question or task used.
- Candidate response or relevant excerpt.
- What a sufficient response needed to demonstrate.
- What the student demonstrated.
- What was missing or incorrect.
- Recommended improvement.
- Evidence confidence or coverage.

Example:

**Competency:** Binary search and complexity analysis
**Observation:** The student identified that the search space is reduced by half but could not explain the invariant or derive the logarithmic time complexity.
**Recommendation:** Review the binary-search invariant and practice explaining why each iteration reduces the remaining search space.
**Evidence:** Strict Interview 02, Question 4, candidate response excerpt.

## 12.4 Not Assessed must remain distinct from weak

If the student was never asked about DBMS, operating systems, or another competency, the report must say **Not Assessed** rather than assigning a low score.

The platform should show assessment coverage and confidence. One question may provide limited evidence; multiple varied questions may provide stronger evidence.

## 12.5 Strict and Guided evidence must be distinguished

Strict Interview evidence represents unaided performance, subject to transcription and task limitations.

Guided Interview observations represent assisted practice and learning behavior. They may inform recommendations but must remain separately labeled.

The system must not merge assisted answers into an unaided competency score without an explicit, validated assessment method.

## 12.6 Example report structure

A report may contain:

1. Preparation objective and track name.
2. Interview session details.
3. Overall summary.
4. Competency-by-competency findings.
5. Strengths demonstrated.
6. Weaknesses and missing reasoning.
7. Candidate quotes and question references.
8. Assessment coverage and confidence.
9. Areas not assessed.
10. Role/JD alignment matrix, where applicable.
11. Recommended learning actions.
12. Suggested next interview.

## 12.7 Avoid misleading hiring predictions

The platform should not make unsupported claims such as “You have an 85% chance of being hired.”

Instead, use carefully defined outcomes such as:

- Strong evidence of alignment in the assessed areas.
- Partial alignment; some requirements need improvement.
- Significant gaps identified in assessed competencies.
- Insufficient evidence to evaluate the target role comprehensively.

A readiness report is a preparation aid, not a hiring decision.

---

# 13. The Student Improvement Cycle

The improvement cycle connects interview assessment to practical learning and future practice.

## 13.1 Standard cycle

1. **Interview:** The student completes a Strict or Guided session.
2. **Review:** The student receives an appropriate report or learning summary.
3. **Identify gaps:** The system identifies concepts or competencies that need attention.
4. **Recommend practice:** The platform suggests explanations, exercises, examples, or external resources.
5. **Practice:** The student learns and works through relevant activities.
6. **Return:** The student continues the same Preparation Track or creates another one.
7. **Observe progress:** New Strict Interview evidence can be compared with earlier Strict Interview evidence for that track.

## 13.2 Example improvement cycle

A student struggles with binary search during a DSA Strict Interview.

The report explains that the student understands the broad idea but cannot confidently explain the search invariant or complexity.

InterviewCopilot recommends:

- Review the binary-search invariant.
- Work through a visual example.
- Solve a basic binary-search problem.
- Solve a variation involving a rotated sorted array.
- Explain the time and space complexity aloud.

If Guided Interview is available, the student can also practice the concept in an interview-style conversation with optional hints.

When the student feels ready, they may voluntarily start another Strict Interview. That interview should use new or appropriately varied questions so the system can observe independent understanding rather than memorized answers.

## 13.3 Improvement history

For each Preparation Track, the platform should preserve:

- Strict Interview results over time.
- Guided Interview learning observations.
- Competency trends.
- Previous weak areas.
- Topics that have improved.
- Topics still needing attention.
- Recommended next steps.

The interface should distinguish improvement demonstrated in Strict sessions from progress observed during Guided practice.

---

# 14. Multiple Tracks, Companies, Subjects, and Sessions

This is a core requirement. One student may prepare for several subjects, roles, and companies at the same time.

## 14.1 Shared candidate profile, separate tracks

The Candidate Context Vault is shared across the account. Preparation Tracks remain logically separate.

Each track keeps its own:

- Preparation objective and configuration.
- Interview Brief versions.
- Interview Sessions.
- Strict Interview attempt count.
- Guided Interview eligibility state.
- Assessment reports.
- Improvement recommendations.
- Competency history for that objective.

This prevents a poor DSA result from unlocking Guided Interview for an unrelated company-specific track.

## 14.2 Example set of concurrent tracks

| Display name | Track type | Objective | Independent history? |
|---|---|---|---|
| Data Structures & Algorithms | Topic | Arrays, trees, graphs, DP, complexity | Yes |
| Database Fundamentals | Topic | SQL, normalization, indexing, transactions | Yes |
| Backend Engineer Intern | Role | General backend engineering preparation | Yes |
| Northstar Technologies — Backend Engineer Intern | Company/JD | Specific fictional company and JD | Yes |
| Embedded Systems Engineer | Role | Embedded and electronics preparation | Yes |

## 14.3 Session naming convention

Use a consistent naming pattern so the student can understand the history.

Examples:

- `DSA — Strict Interview 01`
- `DSA — Strict Interview 02`
- `DSA — Strict Interview 03`
- `DSA — Guided Interview 01`
- `DBMS — Strict Interview 01`
- `Backend Engineer Intern — Strict Interview 01`
- `Northstar Technologies / Backend Engineer Intern — Strict Interview 01`

A future UI may also show a date and session number.

## 14.4 Track-specific Guided unlock state

Example:

| Preparation Track | Strict sessions completed | Guided status |
|---|---:|---|
| DSA | 3 | Unlocked after insufficient combined performance |
| DBMS | 2 | Locked; three initial sessions not yet completed |
| Backend Engineer Intern | 3 | Locked because performance was satisfactory |
| Northstar Technologies — Backend Intern | 1 | Locked; initial sequence in progress |

The example is illustrative. The precise performance threshold remains to be defined and validated.

## 14.5 Cross-track context and evidence

Candidate context can be reused across tracks when relevant. For example, a project from the Candidate Context Vault may be discussed in both a general backend role track and a specific company track.

However:

- Each track should preserve its own interview objective and history.
- A result from one track should not automatically change another track's Guided unlock state.
- Shared competency evidence may be displayed as context, but should not silently replace track-specific assessment.
- Any cross-track transfer of evidence must be visible, explainable, and governed by a clear policy.

---

# 15. Worked Example: One Student Using InterviewCopilot

This example demonstrates how one student can use several tracks while maintaining a shared Candidate Context Vault.

## 15.1 Student background

**Student:** Aarav (fictional example)
**Academic background:** Third-year Computer Science student
**Career goals:** Backend engineering and software engineering internships
**Profile inputs:** Resume, academic details, two projects, one internship, skills, and a detailed onboarding conversation.

### Candidate Context Vault summary

- Education: Computer Science undergraduate.
- Programming: Python, Java, SQL (self-reported).
- Project 1: Recommendation system.
- Project 2: Computer vision application.
- Internship: Backend development at a startup.
- Personal context: Comfortable explaining project goals, but has limited formal interview experience.

The profile records which details are candidate-reported, document-derived, or confirmed. Interview performance later provides separate evidence about demonstrated competency.

## 15.2 Track A — Data Structures & Algorithms

**Track name:** `Data Structures & Algorithms`
**Track type:** Topic-based
**Scope:** Arrays, strings, binary search, trees, graphs, complexity analysis
**Initial mode:** Strict Interview

| Session | Mode | Example outcome |
|---|---|---|
| DSA Strict Interview 01 | Strict | Struggles with problem decomposition and complexity analysis |
| DSA Strict Interview 02 | Strict | Understands basic arrays but struggles with binary-search reasoning |
| DSA Strict Interview 03 | Strict | Continues to show gaps across multiple DSA competencies |

After the third completed Strict Interview, the system reviews the combined evidence. In this illustrative case, the evidence indicates insufficient performance, so Guided Interview is unlocked for the DSA track only.

Aarav later chooses:

- DSA Guided Interview 01: Requests a hint on binary search.
- DSA Guided Interview 02: Works through tree traversal and recursion with optional explanations.

He can then voluntarily start DSA Strict Interview 04 when he wants another independent interview. Guided Interview remains available.

## 15.3 Track B — Database Fundamentals

**Track name:** `Database Fundamentals`
**Track type:** Topic-based
**Scope:** SQL, joins, normalization, indexing, transactions
**Initial mode:** Strict Interview

Aarav has only completed two Strict sessions. Guided Interview remains locked because the three-session initial sequence has not yet been completed.

This track has its own interview plan, evidence, and unlock state. The DSA result does not unlock Guided Interview for DBMS.

## 15.4 Track C — Backend Engineer Intern

**Track name:** `Backend Engineer Intern`
**Track type:** Role-based
**Objective:** General backend engineering preparation without a specific company.

The interview covers relevant areas such as:

- Programming fundamentals.
- APIs and HTTP.
- Databases.
- Backend architecture.
- Debugging and practical reasoning.
- Project and internship ownership.
- Behavioral examples.

The role track can reuse Aarav's internship details from the Candidate Context Vault. It has separate sessions and its own Strict/Guided state.

## 15.5 Track D — Company-specific preparation

**Track name:** `Northstar Technologies — Backend Engineer Intern — JD v1`
**Track type:** Company/JD-based
**Company:** Northstar Technologies (fictional)
**Role:** Backend Engineer Intern
**Input:** A supplied job description.

The preparation process:

1. Reads the JD and extracts required and preferred competencies.
2. Selects relevant candidate context from Aarav's profile.
3. Researches relevant public company information and stores source references.
4. Separates verified facts from anecdotal reports and system inferences.
5. Creates an Interview Brief and an interview blueprint.
6. Begins a company/role-specific Strict Interview.

The company-specific track does not inherit DSA's Guided unlock status. It starts with its own Strict Interview sequence.

## 15.6 What the student sees on the dashboard

| Preparation Track | Latest activity | Mode availability |
|---|---|---|
| Data Structures & Algorithms | Guided Interview 02 completed | Strict and Guided available |
| Database Fundamentals | Strict Interview 02 completed | Strict available; initial sequence not complete |
| Backend Engineer Intern | Strict Interview 01 completed | Strict available |
| Northstar Technologies — Backend Intern | Interview Brief ready | Strict available |

The Candidate Context Vault is shared, but each track remains distinct and understandable.

---

# 16. Feature Catalogue

## 16.1 Core features

| Feature | Description | Priority |
|---|---|---|
| Student account | Registration, authentication, and profile settings | MVP |
| Conversational onboarding | AI-led discovery of academic and practical experience | MVP |
| Resume upload | PDF/DOCX upload and extraction | MVP |
| Candidate Context Vault | Structured, editable candidate profile | MVP |
| Project and internship deep context | Detailed ownership, implementation, decisions, and outcomes | MVP |
| Preparation path selection | Topic, role, and company/JD paths | MVP |
| Preparation Tracks | Independent objectives, sessions, and histories | MVP |
| JD analysis | Extract required and preferred competencies | MVP for company/JD path |
| Company research | Public research with dates, sources, and confidence labels | MVP for company path |
| Interview Brief | Structured, versioned interview plan | MVP |
| Hybrid interviewer | Planned coverage with adaptive follow-ups | MVP |
| Text interview | Text conversation and transcript | MVP |
| Voice interview | Speech input and spoken questions | MVP target; rollout may be staged |
| Strict Interview | Independent interview without assistance | MVP |
| Three-session Guided unlock policy | Track-specific eligibility rule | MVP |
| Guided Interview | Optional progressive hints and explanations | MVP after unlock |
| Session history | Previous interview sessions and transcripts | MVP |
| Evidence-based assessment | Findings tied to questions and answers | MVP |
| Not Assessed state | Explicitly marks areas without sufficient evidence | MVP |
| Target-role readiness report | Alignment with selected role/JD | MVP |
| Improvement recommendations | Weakness-specific next steps | MVP |
| Multiple active tracks | Parallel preparation across subjects, roles, and companies | MVP |

## 16.2 High-value additions

| Feature | Description | Suggested phase |
|---|---|---|
| AI profile-enrichment interview | Deep onboarding conversation about projects and internships | MVP/early follow-up |
| Project Defense Mode | Focused questioning on a selected project | Early follow-up |
| Resume-to-question traceability | Explains why each question was asked | Early follow-up |
| Personal question bank | Stores difficult questions for revision | Early follow-up |
| Interview replay | Transcript with timestamps, question links, and feedback markers | Early follow-up |
| Interview deadline mode | Prioritizes preparation before a known interview date | Early follow-up |
| Answer evolution tracking | Compares explanations across sessions | Early follow-up |
| Preparation workspace | Notes, code, explanations, and study artifacts | Later |
| Coding execution | Isolated code editor and test execution | Later / domain-specific |
| SQL execution | Controlled database exercises | Later / domain-specific |
| Interviewer personalities | Friendly, senior technical, strict, engineering manager styles | Later |
| Panel interview simulation | Multiple interviewer personas | Later |
| Multilingual preparation | Regional-language explanations and interview practice | Later |
| Video interviews | Video-based practice, with carefully bounded feedback | Later |
| University dashboards | Consented institutional reporting and placement support | Later / B2B |

## 16.3 Feature principle

A feature should be included because it improves candidate understanding, interview realism, assessment quality, or learning outcomes—not simply because it uses AI.

---

# 17. Suggested Product Screens and Navigation

The following is a conceptual information architecture, not a finalized UI design.

## 17.1 Main navigation

- **Dashboard:** Overview, active tracks, recent sessions, and next steps.
- **My Profile:** Candidate Context Vault and onboarding completion.
- **Preparation Tracks:** Topic, role, and company-specific tracks.
- **Interview History:** Search and review past sessions.
- **Learning Workspace:** Recommended topics, notes, and practice activities.
- **Settings:** Account, privacy, data, audio, and accessibility preferences.

## 17.2 Important screens

1. Landing and sign-up.
2. Basic profile setup.
3. Conversational onboarding interface.
4. Candidate Context Vault review/edit screen.
5. Student dashboard.
6. Create Preparation Track screen.
7. Topic-based preparation configuration.
8. Role-based preparation configuration.
9. Company/JD preparation configuration.
10. Interview preparation progress screen.
11. Interview plan summary.
12. Voice/text interview workspace.
13. Strict/Guided mode selector, where eligible.
14. Post-session assessment report.
15. Guided learning and hint interface.
16. Track history and improvement timeline.
17. Multi-track dashboard and track settings.

## 17.3 Dashboard behavior

The dashboard should distinguish:

- Active preparation tracks.
- Tracks awaiting the three initial Strict interviews.
- Tracks where Guided Interview has become available.
- Recent completed sessions.
- Upcoming interview deadlines.
- Recommended learning actions.
- Profile items that require student review.

A student should be able to see clearly which track they are working on before starting an interview.

---

# 18. Product Principles, Quality, Privacy, and Trust

## 18.1 Truthful candidate representation

The platform must never invent an internship, project contribution, achievement, skill, or measurable result. AI suggestions must be marked as suggestions until confirmed.

## 18.2 Evidence-based assessment

Important conclusions must link to actual interview evidence. The platform must distinguish between claimed skill, document-supported experience, and interview-demonstrated ability.

## 18.3 Fairness across disciplines

Evaluation must use domain-appropriate rubrics. A computer science rubric should not be reused for electronics or finance without adaptation.

## 18.4 Accessibility and modality fairness

Students should be able to use text when voice is unsuitable. Speech recognition errors, connectivity problems, accents, disabilities, or assistive technology use must not be mistaken for a lack of knowledge.

## 18.5 Candidate control

Students should be able to review and correct their profile, choose which experiences are relevant to an interview, remove outdated items, and manage their documents and data.

## 18.6 Privacy and data protection

Resumes and experience records contain personal information. The platform should provide:

- Secure authentication and access controls.
- Encryption in transit and at rest.
- Clear retention and deletion rules.
- User access to profile and interview data.
- Explicit consent for any secondary use of data.
- Secure object storage for uploaded documents and media.
- Appropriate logging without exposing sensitive candidate content unnecessarily.
- Warnings against uploading confidential employer or client information without permission.

## 18.7 Research integrity

Company research must preserve sources and dates. Public anecdotes must not be presented as guaranteed interview questions or current official processes.

## 18.8 No false hiring guarantees

Readiness is an estimate of demonstrated alignment in the assessed areas, not the probability of receiving an offer.

## 18.9 Avoid unsupported personality judgments

The platform should evaluate job-relevant communication and behavioral evidence, not infer character, culture fit, intelligence, or hiring suitability from appearance, accent, identity, or other inappropriate proxies.

## 18.10 User-respecting Guided mode

Guided Interview should encourage learning without shaming the student. Hints must be optional. The student should be able to continue the conversation without requesting help.

---

# 19. Conceptual Data and Storage Direction

This section records a product-level storage direction. It does not prescribe the final schema or agent architecture.

## 19.1 Suggested primary storage

**Recommendation: PostgreSQL as the primary relational database**, with JSONB for flexible structured outputs where appropriate.

Reasoning:

- Users have multiple profiles and experiences.
- Each user can have multiple Preparation Tracks.
- Each track can have multiple Interview Sessions.
- Each session contains ordered conversation turns and evaluation evidence.
- The platform needs historical queries and trend analysis.
- Track-specific unlock status and report relationships are naturally relational.

MongoDB could also store these records, but a separate MongoDB database is not required merely because AI outputs are flexible. PostgreSQL plus JSONB is a practical starting point.

## 19.2 Suggested storage responsibilities

| Data | Suggested storage |
|---|---|
| User/account records | PostgreSQL |
| Candidate profile fields | PostgreSQL |
| Flexible extracted profile structures | PostgreSQL JSONB where useful |
| Preparation Tracks | PostgreSQL |
| Interview Brief versions | PostgreSQL, with structured JSON where useful |
| Interview Sessions | PostgreSQL |
| Individual conversation turns | PostgreSQL |
| Assessment evidence and reports | PostgreSQL, with structured JSON where useful |
| Resume and uploaded documents | Object storage; metadata in PostgreSQL |
| Audio recordings, if retained | Object storage with explicit retention policy |
| Semantic retrieval index, if needed | pgvector or another suitable vector store |

## 19.3 Conceptual entities

- User
- CandidateProfile
- EducationRecord
- SkillRecord
- ProjectRecord
- ExperienceRecord
- AchievementRecord
- CandidateDocument
- PreparationTrack
- TrackConfiguration
- JobDescription
- CompanyResearchItem
- InterviewBrief
- InterviewSession
- InterviewTurn
- Question/Task
- Competency
- EvaluationRubric
- AssessmentReport
- GuidedAssistanceEvent
- LearningRecommendation
- ProgressObservation

## 19.4 Important persistence rules

- Candidate profile data is shared across tracks.
- A track has its own session history and unlock state.
- Each Interview Brief is versioned or snapshotted for the session it configures.
- Completed reports should not silently change when the JD or research changes later.
- Conversation turns should be stored individually and in order.
- Strict and Guided evidence should be distinguishable.
- The system should be able to trace an assessment statement to the underlying interview turn(s).

---

# 20. MVP Scope and Suggested Delivery Phases

## 20.1 MVP objective

Build a coherent end-to-end experience for a student to create a profile, start a preparation track, complete realistic interviews, receive trustworthy feedback, and continue improving.

## 20.2 Suggested MVP capabilities

1. Authentication and student account.
2. Conversational profile onboarding.
3. Resume upload and parsing.
4. Candidate Context Vault with review and editing.
5. Topic, role, and company/JD Preparation Tracks.
6. JD extraction for company-specific preparation.
7. Public research with source references for company tracks.
8. Structured Interview Brief.
9. Planned interview structure with adaptive follow-ups.
10. Text interview experience.
11. Voice interview capability, potentially staged after text validation.
12. Strict Interview mode.
13. Three-session, track-specific Guided unlock policy.
14. Guided Interview with optional progressive help.
15. Session history and transcript.
16. Evidence-based assessment.
17. Target-role readiness report.
18. Weakness-specific improvement recommendations.
19. Multiple independent tracks per student.

## 20.3 Suggested phases

### Phase 1 — Product foundation

- Accounts and authentication.
- Candidate Context Vault.
- Conversational onboarding.
- Resume/document extraction.
- Track creation and management.

### Phase 2 — Preparation intelligence

- Topic and role configuration.
- Company/JD preparation.
- Company research and source tracking.
- Interview Brief generation.
- Interview blueprint and rubrics.

### Phase 3 — Interview experience

- Text interview.
- Voice interview.
- Hybrid planned/adaptive question behavior.
- Transcript and session persistence.
- Strict Interview.

### Phase 4 — Assessment and Guided unlock

- Evidence-linked assessment.
- Coverage and confidence reporting.
- Three-Strict-session track policy.
- Guided Interview and progressive hints.
- Separate capture of assisted learning observations.

### Phase 5 — Improvement and expansion

- Learning recommendations.
- Personal question bank.
- Interview replay.
- Improvement timeline.
- Domain pack expansion.
- Coding and other practical assessment tools.

The phases are a suggested sequence. Actual prioritization should follow prototype testing and the team's implementation capacity.

---

# 21. Market Context and Differentiation

## 21.1 Market context

AI mock interviewing, resume/job-description-based preparation, voice conversations, adaptive follow-up questions, and interview feedback already exist in the market. InterviewCopilot should not be positioned as the first product to offer these individual capabilities.

Examples of relevant products include:

- **Mentari:** Its published terms describe voice or text AI mock interviews planned from a resume, role/company information, an optional JD, and public company research. It describes competency scorecards tied to candidate-response quotes, resume review, and learning plans.
- **Huru:** Its official product information describes conversational mock interviews with follow-up questions, job-description or role-based preparation, per-answer feedback, and progress features. Its official press page states that its consumer features became free on 28 September 2026; pricing and availability should be rechecked before making business decisions.
- **Aced (formerly Exponent):** Offers peer and AI practice across areas such as DSA, system design, behavioral interviews, SQL, data science/ML, and other professional topics. Its pages describe transcripts and rubric-oriented AI feedback for supported sessions.
- **Yoodli:** Provides AI roleplays, AI tutoring, and coaching workflows, particularly for organizational learning and high-stakes communication practice. It is broader than a student-only interview preparation product.

This is a selected competitor snapshot, not a complete market map. Product features, prices, and availability change; recheck official pages before using this information in a launch plan.

## 21.2 Proposed differentiation

InterviewCopilot should differentiate through the combined experience rather than claiming that any one feature is unique.

| Product area | InterviewCopilot direction |
|---|---|
| Candidate understanding | Deep Candidate Context Vault with conversational discovery of actual contributions and decisions |
| Candidate evidence | Clear distinction between candidate claims, documents, AI inferences, and demonstrated ability |
| Multiple objectives | Separate, continuing tracks for topics, roles, companies, and JDs |
| Interview behavior | Planned structure with adaptive follow-up questions and coverage control |
| Mode philosophy | Strict-first, with Guided Interview unlocked only after three completed Strict attempts and insufficient performance on that track |
| Guided experience | Optional, progressive, teacher-like assistance inside a continuing interview conversation |
| Assessment | Evidence-linked conclusions, confidence, coverage, and explicit Not Assessed states |
| Improvement | Track-specific learning recommendations and historical progress while keeping Strict and Guided evidence separate |
| Domain support | Shared platform with extensible academic and professional domain packs |

## 21.3 Positioning recommendation

Position InterviewCopilot as:

**“An AI interview preparation companion that understands your real experience, interviews you for your chosen goal, and helps you improve with evidence-based feedback and optional guided practice.”**

The product should compete on the quality and continuity of the candidate experience, the reliability of assessment, and the usefulness of the improvement loop—not merely the number of generated questions.

---

# 22. Product Success Measures

The product should measure whether students complete meaningful practice and improve—not just whether they upload a resume or generate questions.

## 22.1 Activation

- Account creation completion.
- Candidate onboarding completion.
- Candidate profile review/confirmation rate.
- First Preparation Track created.
- First interview started and completed.

## 22.2 Engagement and retention

- Students who complete a second session in the same track.
- Active Preparation Tracks per student.
- Return rate after receiving an assessment report.
- Use of recommended learning activities.
- Repeat use of Guided Interview after unlock.

## 22.3 Interview quality

- Interview completion rate.
- Voice transcription correction rate.
- Question relevance feedback.
- Interview plan coverage.
- Rate of unsupported or untraceable assessment claims.
- Student-reported realism and usefulness.

## 22.4 Learning and improvement

- Weakness-specific practice completion.
- Change in independently demonstrated competency across Strict sessions.
- Reduction in recurring errors, where comparable evidence exists.
- Student-reported clarity about what to improve.
- Rate at which students voluntarily return to Strict Interview after Guided practice.

The last metric is an observation, not a required graduation condition. Guided Interview must remain available after unlock.

## 22.5 Trust and quality

- Candidate corrections to AI-extracted profile information.
- Rate of incorrect profile claims detected.
- Rate of assessment conclusions with supporting evidence.
- User data deletion and export success.
- Research source freshness and quality.
- Accessibility and transcription issue reports.

Avoid optimizing only for higher scores. The system should reward accurate measurement and genuine learning, even when an honest assessment shows that a student is still struggling.

---

# 23. Open Decisions for the Next Design Stage

The product direction is established, but several detailed decisions should be made before finalizing technical architecture and implementation.

## 23.1 Guided unlock calibration

- What competency threshold or qualitative rule should define consistently insufficient performance?
- How should mixed results across the three sessions be interpreted?
- What minimum evidence coverage is required before making an unlock decision?
- Should the system explain exactly why Guided Interview was unlocked?

The three-session rule is established; the exact performance threshold remains open.

## 23.2 Initial domain validation

The architecture should support all disciplines. The first domains selected for deep question and rubric validation still need to be chosen.

## 23.3 Interview duration and configuration

- Which default durations should be offered?
- Should students choose between short, standard, and extended interviews?
- How much control should they have over topic coverage?

## 23.4 Voice experience

- Which languages should be supported initially?
- Should spoken AI responses be available in the first public version?
- What transcription correction and accessibility controls are required?

## 23.5 Practical assessment

- Which domains need code execution first?
- Should SQL, engineering calculations, or other practical exercises be included in the first validated domain packs?

## 23.6 Research policy

- How recent must company research be to count as current?
- Which sources qualify for higher confidence?
- How should source conflicts be displayed?

## 23.7 Learning content

- Should InterviewCopilot generate concept explanations directly?
- Should it curate external learning resources?
- Should the student be able to add their own notes and study material?

## 23.8 Monetization and institutional use

- Free versus paid interview limits.
- Subscription tiers.
- AI usage budgets.
- University/placement-cell offerings.
- Consent and data separation for institutional reporting.

## 23.9 Agent and service architecture

The detailed agent design, agent responsibilities, prompt specifications, tool permissions, orchestration flow, API contracts, and final database schema are intentionally deferred to a later design document. This product document establishes the user experience and product requirements those technical designs must support.

---

# 24. Glossary

| Term | Meaning |
|---|---|
| InterviewCopilot | The AI-powered interview preparation and readiness platform |
| Candidate Context Vault | Persistent, student-controlled collection of academic, professional, project, and personal context |
| Preparation Path | One of the entry choices: topic-based, role-based, or company/JD-based |
| Preparation Track | A continuing preparation objective with its own sessions, history, assessments, and mode eligibility |
| Interview Session | One individual interview attempt inside a track |
| Interview Brief | Structured preparation context and plan for an interview session |
| Domain Pack | Subject-specific question, knowledge, and evaluation resources |
| Strict Interview | Normal, realistic interview without hints or teaching |
| Guided Interview | Normal interview with optional progressive hints, explanations, and teacher-like support |
| Assessment Report | Evidence-based summary of demonstrated performance and gaps |
| Target-Role Readiness | Evidence-based alignment with selected role or JD requirements; not a hiring probability |
| Improvement Cycle | Feedback, targeted practice, another interview, and observed progress |
| Not Assessed | A competency for which sufficient interview evidence was not collected |

---

# 25. Reference Links

The following official product pages were reviewed for the selected market-context snapshot on **30 October 2026**. They are references for product research, not endorsements.

1. **Mentari — Terms of Service:** https://mentari.in/terms
   Describes the product's resume, role/company, optional JD, public research, voice/text interviews, quote-linked scorecards, resume review, and learning-plan workflow.

2. **Huru — Official Product Website:** https://huru.ai/
   Describes conversational mock interviews, JD/role-based practice, answer feedback, and progress features.

3. **Huru — Press and Facts:** https://huru.ai/press/
   Official product facts and pricing/availability statements. Recheck before relying on pricing.

4. **Aced — Mock Interview Practice:** https://www.aced.io/practice
   Describes peer and AI practice across technical and professional interview categories.

5. **Aced — System Design Mock Interviews:** https://www.aced.io/practice/system-design-mock-interviews
   Describes peer practice, AI practice, and supported interview categories.

6. **Yoodli — Roleplays:** https://yoodli.ai/platform/roleplays
   Describes AI roleplays, tutors, rubrics, and coaching workflows.

7. **Yoodli — Overview:** https://support.yoodli.ai/en/articles/9550461-yoodli-overview
   Describes the platform's roleplay, tutor, and coaching capabilities.

---

## Closing Product Statement

InterviewCopilot should help students move from uncertainty to informed preparation.

It begins by understanding the student's real academic and practical experience. It creates separate preparation journeys for different subjects, roles, and companies. It conducts realistic Strict Interviews so students can discover what they can genuinely demonstrate. When a student struggles across three completed Strict Interview attempts in a particular track, Guided Interview can become available as a supportive, optional learning experience. The student remains free to continue normally, request help when needed, and choose when to attempt another Strict Interview.

The platform's long-term value comes from continuity: it remembers the student's context, preserves each preparation track, connects feedback to evidence, and helps the student make measurable progress without pretending to predict an employer's hiring decision.

**InterviewCopilot: Know your story. Face your interview. Close your gaps.**
