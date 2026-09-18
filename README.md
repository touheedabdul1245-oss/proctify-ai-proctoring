# PROCTIFY — AI-Assisted Online Examination Proctoring System

An AI-assisted online examination platform: **admins** manage users, classes and
enrollment; **teachers** author, schedule, publish and *grade* exams; **students**
take them under **live AI proctoring**; **teachers review** AI-raised incidents
and **release** results.

> **Current status — complete (Stages 1–5).** Stage 1 built the platform
> foundation (roles, users/classes/enrollment, exam authoring → scheduling →
> publishing). Stage 2 delivered the student examination workflow (session
> lifecycle, autosave, auto-submit, server-side auto-grading). Stage 3 added the
> pure **AI proctoring engine** (risk bands, sustained events, incidents,
> evidence). Stage 4 exposed the **teacher live-monitoring + review** surface
> (incidents are *suspicion-only* — the teacher’s review is the final verdict).
> Stage 5 completed the product: a **browser→server live proctoring feed**, the
> **result lifecycle** (grade → publish → release + CSV export), **notifications**
> and **analytics**.

---

## Roles

| Role | Access |
|------|--------|
| **Admin** | User management, students + bulk enrollment (CSV), classes/batches, admin dashboard with platform stats and **AI health panel**. |
| **Teacher** | Create exams, MCQ questions, schedule/publish/reschedule/archive; **Live Monitor** (per-session risk + incidents + evidence + review actions); **Results** (scorecards, publish, CSV export); **Analytics** (overview + per-exam distributions). |
| **Student** | `My Exams` (start/continue/resume, result-ready badges), **live proctoring while taking the exam**, result detail after release, **My Results**, notification bell. |

Login redirects by role: `/admin`, `/teacher`, `/student`.

---

## What's implemented

### Platform core (Stages 1–2)
- Auth & JWT (HS256) with role-based RBAC and per-route role checks.
- Users, students, classes, enrollment (single + bulk CSV with row validation).
- Exam state machine `DRAFT → SCHEDULED → AVAILABLE → ACTIVE → COMPLETED → ARCHIVED`,
  audit-logged on every mutation.
- Exam authoring (auto code `EX-XXXXXXXX`, MCQ with 4 options + correct answer,
  negative marking), schedule/reschedule/publish, assignment to students/batches.
- Student exam workflow: session create → readiness wizard → start → timer-driven
  paper with autosave/heartbeat/resync → submit (manual / timeout `EXPIRED`) →
  server-side auto-grading with negative marks → submission summary.

### AI proctoring engine (Stage 3)
- **Read-only AI service layer** (never retrained/downloaded here): custom-trained
  **YOLO** phone/earphone weights (`PROCTIFY_YOLO_WEIGHTS_DIR`), **MediaPipe**
  face/gaze, **PnP** head-pose, **audio/speech** interface. `GET /api/ai/health`
  + `POST /api/ai/verify`.
- Pure, deterministic `SessionRisk` engine: observations → event candidates →
  **sustained confirmation** (≥ per-family sustain window) → per-family
  **cooldown** gating → distinct **repeat runs** (a run re-counts only after a
  `EVENT_REPEAT_RESET_SECONDS` gap) → **incident candidates**.
- Risk bands with hysteresis and factor-weighted index; every band change persists
  a `risk_scores` snapshot.
- **Nothing auto-verdicts.** The engine only reports; incidents are created
  `PENDING` (deduped per session+type) and only a teacher’s review closes them.
- Evidence images stored under `datastore/evidence/<session_token>/`, served back
  via `/api/evidence/{path}` (traversal-guarded).

### Live proctoring + monitoring (Stage 4)
- Teacher **Live Monitor**: sessions with risk level, live state, pending review
  counts, camera/mic, recent events; per-session risk history bars, AI event
  timeline, incident cards with review actions (CONFIRM / DISMISS / RESOLVE) and
  teacher remarks; evidence thumbnails.
- Shared **per-session engine registry**: one engine instance per active session
  (bounded, thread-safe), dropped when the session closes — so sustained signals
  graduate across requests and monitoring reflects the *same* engine state.

### Final product (Stage 5)
- **Student live feed** (browser→server): the exam paper captures camera frames,
  downsizes to JPEG < 300 KB and posts them at the server-advertised cadence
  (`POST /api/student/sessions/{token}/proctoring`, owner-checked, rate-limited
  with 429 + back-off). The server decodes the frame, runs the AI pipeline and
  feeds the shared per-session engine. Camera-less students still send an honest
  "no camera" observation so coverage gaps surface instead of disappearing.
- **Results**: on submit/expiry the session is graded, a `Result` row is written
  (unique per exam+student), and the engine is released. Teachers see a
  scorecard grid, review detail (with risk + incident context), **publish** a
  result (idempotent, audit-logged, notifies the student) and **export CSV**
  (formula-injection guarded). Students see the published scorecard with a
  per-question answer review and their proctoring summary.
- **Notifications**: per-user inbox (RESULT published, session closed, incident
  raised…), unread count polling and read-all in the top-bar bell.
- **Analytics**: role-aware overview (totals, risk distribution, incident
  pipeline, recent activity) and per-exam drill-down (score distribution,
  question difficulty / facility, incident types, 10-day event trend).

---

## Architecture

```
frontend/  (React + Vite, dev port 5173, proxies /api → 127.0.0.1:8100)
    API_BASE '/api' · AuthContext · role-gated pages (admin/teacher/student)
    hooks/useProctoring.js   live camera feed to the server engine

backend/   (FastAPI package, port 8100)
    main.py            app + CORS + bootstrap admin seed + Stage-5 routers
    config.py          settings (SQL path, JWT, exam states, YOLO weights dir)
    database.py        SQLAlchemy, init_db + Stage-5 migration
    models.py / schemas.py / schemas_stage5.py
    auth.py            JWT + authorize_roles
    routes/            auth · users · classes · exams · students · ai ·
                       proctoring_monitor · student_proctoring (feed) ·
                       result_routes · analytics · evidence_media · notifications
    proctoring/        engine (SessionRisk) · incidents · temporal · constants ·
                       registry (per-session engines)
    ai_service/        service + yolo / mediapipe / pnp / audio interfaces
    services/          proctoring_service (shared ingest+persist) · notifications
datastore/proctify.db   SQL database (primary store); datastore/evidence/  media
```

- **Primary database: SQL** (SQLite by default). Override with `DATABASE_URL`
  (e.g. PostgreSQL) — all storage is relational SQL.
- Frontend dials the backend through `/api` (Vite proxy), API on `8100`.

---

## Run locally

### Prerequisites
- Python 3.10+ · Node 18+ · npm

### 1. Backend (port 8100)

```bash
cd backend
pip install -r requirements.txt          # if requirements.txt exists, else:
pip install fastapi uvicorn sqlalchemy pydantic python-jose[all] passlib[bcrypt] python-multipart
python -m uvicorn backend.main:app --port 8100
```

> Run from the project root so relative package imports resolve
> (`python -m backend.main`). On a fresh/empty DB the app auto-seeds a bootstrap
> admin (see `config.py`: `admin@proctify.dev` / `Admin@123`).

### 2. Frontend (dev, port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` (Vite binds IPv6 `::1` — use `localhost`, not
`127.0.0.1`). If 5173 is taken by another Vite instance, use
`npm run dev -- --port 5174`.

### 3. Default accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@proctify.dev` | `Admin@123` |
| Teacher | `teacher@proctify.dev` | `Teacher@123` |
| Student | `s1@proctify.dev` | `Student@123` |

---

## Testing

Backend suites run against temporary SQLite databases (the real DB is never
touched by tests):

```bash
# Full backend suite (Stages 1–5): pytest
python -m pytest backend/tests -q          # 35 passed

# Stage-2 standalone end-to-end script
python test_stage2_backend.py              # 58 passed

# Frontend unit tests (node --test, no test runner dependency)
cd frontend && node --test                 # 10 passed

# Production build
cd frontend && npm run build               # vite build (66 modules)
```

## Current verification status

- Backend pytest suite (Stages 1–5): **35/35 PASS** — auth, users, classes,
  enrollment, exam CRUD/lifecycle, session workflow, AI health, proctoring engine
  (events/cooldown/repeats/incidents/risk), monitor endpoints + incident review,
  student live feed (rate limit, config gating, persistence + incident
  graduation), results (detail/publish/CSV), analytics, evidence media,
  notifications, migration.
- Stage-2 backend end-to-end: **58/58 PASS**.
- Frontend unit tests: **10/10 PASS**. Production build green.
- API/engine contract verified end-to-end: a sustained repeated observation
  graduates events → persists → surfaces in monitor → creates a PENDING incident
  → teacher CONFIRM/RESOLVE.

> Note: the camera feed requires a browser with camera permission (or falls back
> to the honest "no camera" mode); the YOLO weights directory must be set
> (`PROCTIFY_YOLO_WEIGHTS_DIR`) for real object detection — otherwise the engine
> degrades gracefully on the other signals.