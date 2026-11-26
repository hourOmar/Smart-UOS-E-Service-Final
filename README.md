# Smart UoS E-Service

**An intelligent academic e-service platform with a multi-agent decision support system**
— University of Sharjah Senior Project (final implementation).

Smart UoS E-Service lets University of Sharjah students submit academic service requests online
and follow them to a decision, and gives authorized staff one review page per request with the
student's record, the verified evidence and an advisory AI evaluation. Staff always make the final
decision.

More detail: [frontend/README.md](frontend/README.md) · [backend/README.md](backend/README.md)

---

## Contents

- [Project overview](#project-overview)
- [Project objectives](#project-objectives)
- [Main features](#main-features)
- [AI multi-agent system](#ai-multi-agent-system)
- [Technology stack](#technology-stack)
- [System architecture](#system-architecture)
- [Project structure](#project-structure)
- [Installation and setup](#installation-and-setup)
- [Testing](#testing)
- [Security and data protection](#security-and-data-protection)
- [Known limitations](#known-limitations)
- [Academic project](#academic-project)

---

## Project overview

Academic service requests such as raising a section's capacity, changing programs, requesting an
incomplete exam, or transferring and substituting courses are traditionally handled through
forms, e-mail and manual checks. Each request requires staff to look up the student's transcript,
prerequisites, study plan, deadlines and supporting documents before deciding, which is slow,
repetitive and hard to keep consistent.

Smart UoS E-Service brings these services into one web application:

- **Students** submit requests, attach supporting documents where required, and track every
  request to its final decision and explanation.
- **Staff** review requests with all relevant evidence on one page, assisted by AI agents that
  check the academic rules and recommend an outcome, and then record the decision themselves.

## Project objectives

- **Reduce manual processing** by collecting the student's records, the request details and the
  applicable academic rules automatically for every request.
- **Improve administrative efficiency** with request search, filtering, per-type request lists,
  priority indicators and a consistent review page for each service.
- **Support academic decision-making** with AI agents that apply deterministic academic checks,
  explain their reasoning, and, for rejections, suggest clear explanations to the student.
- **Keep humans in control:** AI recommendations are advisory only; every request is finalized by
  an authorized staff member.
- **Protect student data:** database policies decide who may read or change what, and no
  database credential or AI key ever reaches the browser.

## Main features

### Students

- Sign in with a university account (Supabase Authentication).
- Student dashboard with the service catalog, service search and service details pages.
- Submit five types of academic requests:

  | Service | What the student provides |
  |---|---|
  | **Raise Capacity** | A course section of the current term and a justification |
  | **Program Change** | The requested program and a reason |
  | **Incomplete Exam** (final exams) | The enrolled course section, the missed exam's date and time, an explanation, and optional PDF proofs |
  | **Course Equivalency** | The previously completed course, the requested equivalent course and both syllabi |
  | **Course Substitution** | The original course, the proposed substitute and a reason |

- **My Requests:** every submitted request with its current status.
- **Request details:** the submitted information, supporting documents, progress, and, once
  decided, the final decision and the staff explanation.
- **My Profile:** the student's academic record.

### Administrators (staff linked in `Authorized_Staff`)

- Administrator dashboard: request search, request-type cards and the pending requests table.
- All Requests and per-type request lists with filtering and paging; a **Priority** column for
  Raise Capacity requests.
- Student profile pages with the student's academic record.
- A review page for each of the five request types: request details, student record, supporting
  documents and the AI evaluation with its reasoning and evidence.
- Run or re-run AI evaluations where allowed.
- Approve or reject, with an explanation where required and an explicit confirmation step. For
  rejections, where suggested explanations are available, they can be inserted into the decision
  form and edited before submitting.

## AI multi-agent system

Every agent is a custom Python implementation in [backend/app/agents/](backend/app/agents/) and
follows the same pattern:

1. **Structured evidence:** Python reads the request, the student's record and the relevant
   academic data through a read-only database role (and, where needed, supporting documents or
   official UoS study-plan pages).
2. **Deterministic academic checks:** Python evaluates the verifiable rules (prerequisites,
   grades, completed hours, deadlines, capacity, study plans, transfer limits) against the agent's
   own knowledge files.
3. **Google Gemini** (through the Google GenAI SDK) receives the evidence and the policy and
   returns a structured recommendation with explanations.
4. **Validation and storage:** Python validates Gemini's reply and stores every run, including
   technical failures, in the `agents` database schema as an auditable run history.

| Agent | Package | Request type | Recommendation |
|---|---|---|---|
| Raise Capacity Academic Eligibility Evaluation Agent | `raise_capacity_eligibility/` | Raise Capacity | APPROVE / REJECT / MANUAL_REVIEW |
| Raise Capacity Prioritization Agent | `raise_capacity_priority/` | Raise Capacity | HIGH / MEDIUM / LOW / MANUAL_REVIEW |
| Program Change Eligibility Agent | `program_change_eligibility/` | Program Change | APPROVE / REJECT / REQUIRES_REVIEW |
| Incomplete Exam Eligibility Evaluation Agent | `incomplete_exam/` | Incomplete Exam | APPROVE / REJECT / MANUAL_REVIEW |
| Course Equivalency Eligibility Evaluation Agent | `course_equivalency/` | Course Equivalency | APPROVE / REJECT / MANUAL_REVIEW |
| Course Substitution Eligibility Agent | `course_substitution_eligibility/` | Course Substitution | ELIGIBLE / NOT_ELIGIBLE / MANUAL_REVIEW |
| **Rejection Explanation Agents** | in the Raise Capacity, Incomplete Exam, Course Equivalency and Course Substitution packages | after a rejection recommendation | Three suggested explanations (formal, concise, supportive) |

**Raise Capacity Eligibility Agent.** Checks the course's complete prerequisite and academic
standing requirement (from a validated `course_prerequisites.json` and the student's transcript
and completed hours) and the section's remaining capacity. The verified evidence determines which
recommendation the eligibility policy allows; Gemini's reply must match it or is retried. Students
outside the supported program (Computer Science) receive MANUAL_REVIEW.

**Raise Capacity Prioritization Agent.** Assesses academic urgency from seven factors (graduation
proximity, degree progress, course requirement, course availability, previous attempts,
prerequisite completion, academic progression) under eight prioritization rules. It runs
automatically for In Progress Raise Capacity requests shown in the administrator tables, and the
result fills the Priority column. It never decides eligibility.

**Rejection Explanation Agents.** Run only after a validated rejection recommendation. Python
derives keywords from the confirmed failures; Gemini writes three suggested explanations; Python
validates them against the verified evidence and falls back to templates if needed. Staff can use
and edit a suggestion, or write their own.

**Program Change, Incomplete Exam, Course Equivalency and Course Substitution agents** check, for
example, CGPA and applicable hours and the requested program's study plan (Program Change); the
submission window, enrolment and proof documents (Incomplete Exam); syllabus similarity, grade,
study plan and transfer limits (Course Equivalency); and course availability, level, core status
and offering (Course Substitution).

> **AI recommendations versus final decisions.** All agent outputs are advisory. No agent
> approves, rejects or changes a request. The final decision is recorded only by an authorized
> staff member through a database decision function, may differ from the AI recommendation, and
> is shown separately from it. The AI does not verify the authenticity of uploaded documents.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, React Router, `@supabase/supabase-js`, CSS |
| Backend | Python 3.14, FastAPI, Uvicorn, SQLAlchemy 2 with psycopg 3, Pydantic 2 |
| AI | Google Gemini through the Google GenAI SDK (`google-genai`) |
| Database and identity | Supabase: PostgreSQL with row-level security, Supabase Authentication, private Supabase Storage |
| Testing | Node.js built-in test runner and ESLint (frontend); pytest (backend) |

## System architecture

```
 Browser: React application (public anon key only)
   │
   ├── sign-in, student pages, submissions, decisions ─────► Supabase
   │   (row-level security and database functions)            Auth · PostgreSQL · Storage
   │                                                              ▲
   └── /api/... with the staff member's session token             │ read-only role smart_uos_backend
         ▼                                                         │ (+ the staff session for files)
       FastAPI backend (staff-only AI features) ───────────────────┘
         │  structured evidence, deterministic checks, run history (agents schema)
         ▼
       Google Gemini (advisory recommendations and suggested explanations)
```

- The **frontend** communicates with Supabase directly; what each user may see or do is enforced
  by row-level security policies and database functions.
- The **backend** serves the staff-only AI features. Every route verifies the caller's Supabase
  session and the `Authorized_Staff` link, reads data through the restricted `smart_uos_backend`
  role, and stores every AI run in the `agents` schema.
- **Final decisions** are made in the review pages and recorded by database functions with the
  staff member's own session; the backend never approves or rejects anything.

## Project structure

```
Smart-UOS-E-Service-Final/
├── README.md                     This file
├── frontend/                     React + TypeScript + Vite application (see frontend/README.md)
│   ├── src/
│   │   ├── pages/                Student and administrator pages (forms, dashboards, review pages)
│   │   ├── components/           UI components grouped by feature
│   │   ├── services/             Supabase and backend API access
│   │   ├── hooks/                Data loading and AI evaluation hooks
│   │   ├── utils/  config/  data/  assets/
│   │   └── App.tsx               Routes and protected areas
│   ├── tests/                    Frontend tests (node --test)
│   ├── .env.example              Frontend environment template
│   └── package.json
└── backend/                      FastAPI backend and AI agents (see backend/README.md)
    ├── app/
    │   ├── main.py               FastAPI application, CORS, routers, /api/health
    │   ├── config.py             Settings from environment variables
    │   ├── core/                 Database, authentication, Gemini client, Storage
    │   ├── api/                  Staff-only API routes, one module per feature
    │   ├── course_equivalency/   Syllabus file handling for Course Equivalency
    │   └── agents/               One package per agent, each with its knowledge files
    │       ├── raise_capacity_eligibility/      knowledge_base/
    │       ├── raise_capacity_priority/         knowledge/
    │       ├── program_change_eligibility/      data/
    │       ├── incomplete_exam/                 knowledge_base/
    │       ├── course_equivalency/              knowledge_base/
    │       └── course_substitution_eligibility/ data/
    ├── tests/                    Offline backend tests (pytest)
    ├── requirements.txt          Application dependencies
    ├── requirements-dev.txt      Application + test dependencies
    └── .env.example              Backend environment template
```

The database scripts (tables, policies, functions and maintenance scripts) are kept locally by the
project owner and are not part of this repository.

## Installation and setup

The commands below are for **Windows (Command Prompt)**, run from the repository folder.

### Prerequisites

- Git, Node.js 22.18 or newer (developed with Node.js 24) and Python 3.14 (with the `py` launcher).
- Access to the project's Supabase project and a Google Gemini API key. Ask the project owner for
  the Supabase URL and anon key, the `smart_uos_backend` connection string and test accounts.

### 1. Clone the repository

```cmd
git clone https://github.com/hourOmar/Smart-UOS-E-Service-Final.git
cd Smart-UOS-E-Service-Final
```

### 2. Install the frontend dependencies

```cmd
cd frontend
npm install
```

### 3. Create and activate the backend virtual environment

```cmd
cd ..\backend
py -3.14 -m venv .venv
.venv\Scripts\activate
```

### 4. Install the backend dependencies

```cmd
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs the application dependencies (`requirements.txt`) plus the test
tools.

### 5. Configure the environment variables

```cmd
copy .env.example .env
cd ..\frontend
copy .env.example .env.local
```

- `backend\.env`: `DATABASE_URL` (the `smart_uos_backend` connection), `SUPABASE_URL`,
  `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL`, optional `GEMINI_FALLBACK_MODELS`, and
  `FRONTEND_ORIGINS`. See [backend/.env.example](backend/.env.example).
- `frontend\.env.local`: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` and optional
  `VITE_API_BASE_URL`. See [frontend/.env.example](frontend/.env.example).

Never commit `.env` or `.env.local`; both are excluded by `.gitignore`.

### 6. Run the backend (terminal 1)

```cmd
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Check it at http://127.0.0.1:8000/api/health.

### 7. Run the frontend (terminal 2)

```cmd
cd frontend
npm run dev
```

Open **http://localhost:5173** and sign in with a student or staff account. In development, Vite
forwards every `/api/...` call to the backend on port 8000, so the backend must be running for the
AI panels and the Priority column; sign-in, student pages, submissions and decisions use Supabase
directly.

### Troubleshooting

| Problem | What to check |
|---|---|
| Blank page; "Missing Supabase environment variables" in the browser console | `frontend\.env.local` exists with both `VITE_SUPABASE_*` values; restart `npm run dev`. |
| A review page says the evaluation service could not be reached | The backend is not running on port 8000. |
| The backend answers 401 or 403 | Sign in again; `SUPABASE_URL` / `SUPABASE_ANON_KEY` must belong to the same project as the frontend; the account must be linked in `Authorized_Staff`. |
| The backend answers 503 | `DATABASE_URL` is missing or wrong; it must connect as `smart_uos_backend`. |
| An evaluation fails because Gemini is unavailable | `GEMINI_API_KEY` is missing or invalid, or the service is busy; try again later. |
| Backend code changes have no effect | Restart the backend; it does not reload automatically. |

## Testing

All tests run offline: they do not call Supabase, Storage or Gemini.

```cmd
cd frontend
npm test
npm run lint
npm run build

cd ..\backend
.venv\Scripts\python -m pytest
```

- Frontend: Node.js built-in test runner (`frontend/tests/`), ESLint, and the TypeScript build.
- Backend: pytest (`backend/tests/`), including the agents' deterministic checks, evidence
  building, Gemini reply validation, run handling and API authorization.

## Security and data protection

- The browser holds only the public Supabase anon key. The database connection and the Gemini key
  exist only in the backend's environment.
- The backend connects as the restricted `smart_uos_backend` role, never as `postgres` or with the
  service-role key.
- Every backend route verifies the Supabase session and the `Authorized_Staff` link.
- Supporting documents are read with the signed-in user's own session under Storage policies.
- The Raise Capacity and Incomplete Exam agents do not send the student's name or ID to Gemini.

## Known limitations

- The Raise Capacity agents' academic knowledge covers the Computer Science program; students in
  other programs receive MANUAL_REVIEW.
- The AI does not verify the authenticity of uploaded documents; staff must check them.
- The current academic term for request forms is configured in
  `frontend/src/config/academicTerm.ts`.
- Decision notifications are recorded in the database; students see decisions and explanations on
  the My Requests and request details pages.
- The database scripts are not in this repository, so a new database cannot be created from it.
- There is no end-to-end browser test suite.

## Academic project

This repository contains the final implementation of the **Smart UoS E-Service** Senior Project at
the **University of Sharjah**: a full-stack academic e-service platform with a multi-agent AI
decision support system. It combines a React and TypeScript web application, a FastAPI backend,
a Supabase PostgreSQL database with row-level security, and custom Python agents that use
deterministic academic checks, structured evidence and Google Gemini to support, not replace,
staff decisions.
