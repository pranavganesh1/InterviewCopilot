# InterviewCopilot

> **Know your story. Face your interview. Close your gaps.**
> An agentic, AI-powered interview preparation, simulation, and coaching platform built for students and engineering candidates.

[![Backend Tests](https://img.shields.io/badge/backend%20tests-276%20passed-emerald)](backend/tests)
[![Frontend Tests](https://img.shields.io/badge/playwright%20e2e-94%20passed-emerald)](frontend/e2e)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19.3-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8.3-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248.svg?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![NATS](https://img.shields.io/badge/NATS-JetStream-27AAE1.svg?logo=nats.io&logoColor=white)](https://nats.io)
[![SeaweedFS](https://img.shields.io/badge/SeaweedFS-S3-00B4B6.svg)](https://github.com/seaweedfs/seaweedfs)

---

## 🌟 Overview & Key Capabilities

InterviewCopilot transforms interview prep from generic flashcards into **deep, personalized, conversational simulations** grounded in your real background, claimed projects, and career targets.

```
       +-----------------------------------------------------------+
       |                  Candidate Web App (React 19)             |
       |  Dashboard · Onboarding Coach · Live Workspace · Reports  |
       +-----------------------------+-----------------------------+
                                     | HTTP / REST (Vite / Nginx)
                                     v
       +-----------------------------------------------------------+
       |               Backend API Modular Monolith (FastAPI)       |
       |  Auth · Vault · Track Service · Interview Engine · Admin  |
       +-------+--------------------+--------------------+---------+
               |                    |                    |
        +------v------+      +------v------+      +------v------+
        | PostgreSQL  |      |   MongoDB   |      | SeaweedFS   |
        | Relational  |      | Chats, Logs |      | Resumes, S3 |
        +-------------+      +-------------+      +-------------+
               |
               | NATS JetStream (Async Events)
               v
       +-----------------------------------------------------------+
       |               Feedback & Track Authoring Workers          |
       +-----------------------------+-----------------------------+
                                     |
                                     v
       +-----------------------------------------------------------+
       |                 Multi-Tier LLM Gateway                    |
       |     Groq (Primary) → NVIDIA NIM (Tier 2) → Gemini Flash   |
       +-----------------------------------------------------------+
```

### 🎯 1. Preparation Tracks & Interview Briefs
- **Three Track Types**: Create preparation tracks by **Topic** (e.g., Operating Systems, Concurrency), **Role** (e.g., Backend Engineer, Machine Learning), or **Company + Job Description**.
- **Automated AI Brief Authoring**: Background authoring workers generate comprehensive **Interview Briefs (v1)** complete with:
  - Custom candidate-anchored angles that cross-examine your claimed projects and internships.
  - Categorized competencies (`core`, `important`, `nice_to_have`).
  - Question areas with specific rubrics and 5 pre-validated practice questions.
  - Step-by-step preparation plan.

### 🤖 2. Adaptive AI Onboarding Coach ("Chanakya")
- **Conversational Vault Extraction**: Upload your resume PDF or chat naturally with Coach Chanakya to automatically populate your profile vault (education, internships, projects, skills).
- **Adaptive Background Inference**: Tailors welcoming tone, role suggestions, and topics for technical and non-technical backgrounds alike (Commerce, Physics, CS, etc.).
- **Goal Discovery Flow**: Interactive multi-select for career aspirations, placement targets, and focus domains.
- **Smart Engagement**: Real-time typing dots, soft bubble animations, recovery toasts, and gentle idle nudges.

### 🎙️ 3. Realistic Interview Simulations
- **Two Interview Modes**:
  - **Strict Mode**: Unassisted examination under strict timer constraints; full evaluation and diagnostics generated post-interview.
  - **Guided Mode**: Unlocks after 3 strict attempts, providing Socratic hints when stuck.
- **Four Interviewer Personas**:
  - **Balanced**: Even coverage of concepts, practical application, and clarity.
  - **The Strict Architect**: High scrutiny on system structure, fault tolerance, reliability, and trade-offs.
  - **The Hiring Manager**: Focuses on ownership, delivery, real-world execution, and impact.
  - **The Academic Deep-Diver**: Probes theoretical depth, mathematical complexity, and fundamentals.
- **Resume Anchoring**: Optional toggle to anchor technical questions directly to your uploaded projects.

### 💻 4. Integrated Coding Workspace
- Embedded **Monaco Code Editor** with language syntax highlighting, templates, and multi-language support (Python, JavaScript, TypeScript, Go, C++, Java).
- Automatic question classification for coding vs. conceptual questions.

### 📊 5. Comprehensive Evidence-Based Reports
- **Holistic Diagnostics**: Overall score, turn coverage, strengths, gaps, and question-by-question scoring.
- **Actionable Roadmaps**: Personalized improvement plans identifying specific competencies and weak areas requiring follow-up practice.

### 🛡️ 6. Resume Readiness Audit
- Scans your resume claims and flags items that interviewers will interrogate:
  - Categorized into **Clear**, **Add Detail**, and **Be Ready to Explain**.
  - Provides probable interviewer questions, strengthening tips, and stronger phrasing alternatives with one-click copy.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, TypeScript, Vite 8, Tailwind CSS v4, TanStack Query v5, Monaco Editor, React Router 7 |
| **Backend API** | Python 3.13+, FastAPI, SQLAlchemy (asyncpg), Motor (async MongoDB), Pydantic v2, uv, Ruff |
| **Databases** | PostgreSQL 16 (Relational state & tracks), MongoDB 7 (Chat sessions, logs & context) |
| **Storage & Messaging**| SeaweedFS (S3-compatible resume storage), NATS 2 JetStream (Async queue) |
| **LLM Gateway** | LiteLLM Proxy with 3-tier fallback (`Groq` → `NVIDIA NIM Nemotron-3.5` → `Gemini 2.5 Flash`) |
| **Testing** | Pytest (276 backend tests), Playwright (94 end-to-end browser tests) |

---

## 🚀 Quickstart & Setup

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- [Node.js 20+](https://nodejs.org/) & `npm`
- [Python 3.13+](https://www.python.org/) & [`uv`](https://docs.astral.sh/uv/)

### 1. Clone & Configure Environment
```bash
git clone https://github.com/pranavganesh1/InterviewCopilot.git
cd InterviewCopilot

# Copy the example environment file
cp .env.example .env
```

Configure your API keys in `.env`:
```env
APP_ENV=local
JWT_SECRET=your-secure-random-jwt-secret
SESSION_SECRET=your-secure-random-session-secret

# LLM Providers (at least one key required; multi-tier failover supported)
GROQ_API_KEY=gsk_...
NVIDIA_NIM_API_KEY=nvapi-...
GEMINI_API_KEY=AIzaSy...

# Optional: Google OAuth (for web sign-in)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8080/api/v1/auth/google/callback
```

---

### 2. Run the Full Stack via Docker (Recommended)

To run the entire platform (frontend, backend API, workers, databases, queues, and gateways) with one command:

```bash
cd infra
docker compose --env-file ../.env -f docker-compose.yml up -d --build
```

#### Exposed Local Ports:
| Service | URL | Description |
|---|---|---|
| **Web Frontend** | `http://localhost:8080` | Production React SPA served via Nginx |
| **Backend API** | `http://localhost:8000` | FastAPI server (`http://localhost:8000/docs` for Swagger UI) |
| **LiteLLM Gateway** | `http://localhost:4000` | OpenAI-compatible proxy routing LLM calls |
| **PostgreSQL** | `localhost:5433` | Host-mapped port (avoids Windows 5432 conflict) |
| **MongoDB** | `localhost:27018` | Host-mapped port (avoids Windows 27017 conflict) |
| **SeaweedFS S3** | `http://localhost:9000` | S3 API endpoint for resume storage |
| **NATS Monitor** | `http://localhost:8222` | NATS JetStream monitoring UI |

---

### 3. Hybrid Development Mode (Hot Reloading)

If you are developing backend or frontend code actively and want live reloading:

#### Step 1: Start Supporting Infrastructure Only
```bash
cd infra
docker compose --env-file ../.env up -d postgres mongo nats litellm seaweedfs
```

#### Step 2: Run Backend API & Worker
In Terminal 1 (API):
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In Terminal 2 (Async Feedback Worker):
```bash
cd backend
uv run python -m app.workers.feedback_worker
```

#### Step 3: Run Frontend Dev Server
In Terminal 3:
```bash
cd frontend
npm install
npm run dev
# Accessible at http://localhost:5173 (proxies /api → http://127.0.0.1:8000)
```

---

## 🧪 Testing & Verification

The project is protected by comprehensive test suites ensuring zero regression across LLM gateway routing, track lifecycles, and user interactions.

### Run Backend Tests (276 Tests)
```bash
cd backend
uv run pytest
```

### Run Frontend End-to-End Tests (94 Tests)
```bash
cd frontend
npm run build
npx playwright test
```

### Run Linter & Formatter
```bash
# Backend
cd backend
uv run ruff check app tests
uv run ruff format app tests

# Frontend
cd frontend
npm run lint
```

---

## 📂 Repository Layout

```
InterviewCopilot/
├── backend/                       # FastAPI modular monolith
│   ├── app/
│   │   ├── agents/                # LLM agents (Interviewer, Onboarding Coach, Persona)
│   │   ├── api/v1/                # REST endpoints (auth, onboarding, tracks, interviews, vault)
│   │   ├── core/                  # Security (JWT), configs, structured logging
│   │   ├── db/                    # SQLAlchemy (Postgres), Motor (Mongo), S3 clients
│   │   ├── gateway/               # Multi-tier LLM gateway & structured JSON parsing
│   │   ├── models/                # SQLAlchemy & Pydantic domain models
│   │   ├── services/              # Business logic (vault, readiness, tracks, review)
│   │   └── workers/               # NATS background workers (feedback_worker)
│   └── tests/                     # 276 Pytest unit & integration tests
│
├── frontend/                      # React 19 SPA
│   ├── e2e/                       # 94 Playwright browser end-to-end tests
│   ├── src/
│   │   ├── components/            # UI widgets (CodingWorkspace, GoalDiscovery, Modal, Vault)
│   │   ├── context/               # AuthContext & state providers
│   │   ├── lib/                   # API clients, code templates, personas, status helpers
│   │   └── pages/                 # Dashboard, Onboarding, Interview, Report, Readiness, Admin
│   ├── nginx.conf                 # Container production Nginx reverse proxy configuration
│   └── vite.config.ts             # Vite configuration with Tailwind CSS v4
│
├── infra/                         # Infrastructure & Containerization
│   ├── litellm/                   # LiteLLM router configuration & model fallbacks
│   └── docker-compose.yml         # 8-container orchestration definition
│
└── docs/                          # Architectural designs & specifications
```

---

## 🛡️ Key REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/auth/me` | Fetch authenticated candidate profile and preferences |
| `GET` | `/api/v1/onboarding/state` | Onboarding chat history, coach status, and vault state |
| `POST` | `/api/v1/onboarding/chat` | Send message to AI Onboarding Coach Chanakya |
| `POST` | `/api/v1/vault/resume` | Upload resume PDF for automated entity extraction |
| `POST` | `/api/v1/vault/readiness`| Run AI Resume Readiness audit on parsed claims |
| `GET` | `/api/v1/tracks` | List all active preparation tracks |
| `POST` | `/api/v1/tracks` | Create new track (initiates async brief authoring) |
| `GET` | `/api/v1/tracks/{id}/brief` | Retrieve synthesized interview brief and question bank |
| `POST` | `/api/v1/tracks/{id}/sessions` | Start an interview simulation (strict or guided) |
| `POST` | `/api/v1/sessions/{id}/turns` | Submit answer turn and retrieve next question |
| `GET` | `/api/v1/sessions/{id}/report`| Fetch evaluation feedback report and progression score |

---

## 🤝 Contributing & License

1. Create a feature branch (`git checkout -b feature/amazing-feature`).
2. Verify all test suites pass (`pytest` and `playwright`).
3. Commit your changes (`git commit -m "feat: add amazing feature"`).
4. Push to branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request.

Distributed under the MIT License. See `LICENSE` for more information.
