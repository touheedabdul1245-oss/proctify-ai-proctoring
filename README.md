# PROCTIFY — AI-Assisted Online Examination Proctoring System

An AI-assisted online examination platform: **admins** manage users, classes and
enrollment; **teachers** author, schedule and publish exams; **students** take
them under AI-assisted proctoring.

> **Current status — Stage 2 complete & verified.** Stage 1 built the platform
> foundation (roles, users/classes/enrollment, exam authoring → scheduling →
> publishing). Stage 2 delivers the **student examination workflow**: exam
> session lifecycle (create → readiness wizard → start → take → autosave →
> submit → timeout), server-side auto-grading, and the student result page.
> The AI service layer (YOLO / MediaPipe / PnP / audio) is still integrated at
> the **health/readiness level only** — **live AI proctoring is NOT yet
> implemented** and is the next stage (Stage 3).

---

## Roles

| Role | Access |
|------|--------|
| **Admin** | User management, students + bulk enrollment (CSV), classes/batches, admin dashboard with platform stats and **AI health panel**. |
| **Teacher** | Create exams, add MCQ questions, schedule with a time window, set SCHEDULED / AVAILABLE / publish, reschedule, archive; exams list with per-exam state. |
| **Student** | `Assigned Exams` (start/continue/resume), pre-exam readiness wizard, timer-driven exam paper with autosave, submission, result summary, profile. |

Login redirects by role: `/admin`, `/teacher`, `/student`.

---

## Stage 1 — What's implemented

Backend (FastAPI, SQLite SQL database):
- Auth & JWT (HS256) with role-based RBAC and role guarding on every route.
- Users, students, classes, enrollment (single + bulk CSV with row validation).
- Exam lifecycle with state machine:
  `DRAFT → SCHEDULED → AVAILABLE → ACTIVE → COMPLETED → ARCHIVED`
  enforced by `config.py` transitions; every mutation is audit-logged.
- Exam authoring: create (auto code `EX-XXXXXXXX`), MCQ questions
  (4 options + correct answer), schedule/reschedule, publish.
- **AI service layer (read-side, ready for Stage 2):**
  - **Custom-trained YOLO** model («proctify_phone_earphone_v2») — loaded
    read-only from the `PROCTIFY_V2` weights (never retrained here; wired via
    `PROCTIFY_YOLO_WEIGHTS_DIR`).
  - **MediaPipe** face/landmark interface.
  - **PnP head-pose estimation** (`pnp_interface`).
  - **Audio / speech detection** (`audio_interface`).
  - `GET /api/ai/health` (admin) — per-module health report used by the AI
    health panel. `POST /api/ai/verify` loads/verifies the modules.

Frontend (React 18 + Vite):
- AuthContext + role guards; `/admin/*`, `/teacher/*`, `/student/*` layouts.
- Admin: dashboard (stats + AI health), Users, Students (with table), Bulk
  Enrollment, Classes.
- Teacher: dashboard, exams list, and a full exam editor (Details / Questions /
  Assign / Schedule / Preview; MCQ modal; publish).
- Student: dashboard, Assigned Exams, profile.

## Not implemented (Stage 3+)
- Real-time AI proctoring: sending frames to YOLO/MediaPipe/PnP/audio during a
  live exam, incident detection & flags, anti-cheat alerts.
- AI-based reporting and analytics, teacher live-monitoring of in-progress
  sessions and their incident feeds.

---

## Architecture

```
frontend/  (React + Vite, dev port 5173, proxies /api → 127.0.0.1:8100)
    API_BASE '/api' · AuthContext · role-gated pages (admin/teacher/student)

backend/   (FastAPI package, port 8100)
    main.py            app + CORS + bootstrap admin seed
    config.py          settings (SQL path, JWT, exam states, YOLO weights dir)
    database.py        SQLAlchemy, init_db
    models.py / schemas.py
    auth.py            JWT + authorize_roles
    routes/            auth · users · classes · exams · students · ai
    ai_service/        service + yolo / mediapipe / pnp / audio interfaces
proctify.db            SQL database (primary store) — datastore/proctify.db
```

- **Primary database: SQL** (SQLite by default). Override with `DATABASE_URL`
  (e.g. PostgreSQL) — all storage is relational SQL.
- Frontend dials backend through `/api` (Vite proxy), API on `8100`.

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
`127.0.0.1`). If 5173 is taken by another Vite instance (common when the older
PROCTIFY_V2 project is also running), launch on a free port and open that one:

```bash
npm run dev -- --port 5174    # → http://localhost:5174
```

### 3. Default accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@proctify.dev` | `Admin@123` |
| Teacher | `teacher@proctify.dev` | `Teacher@123` |
| Student | `s1@proctify.dev` | `Student@123` |

---

## Testing

Backend API smoke (61 checks — auth, users, classes, enrollment, exam CRUD,
state transitions, scheduling, publish):

```bash
python tests/stage1_smoke.py            # or wherever the smoke script lives
```

Browser UI smoke (`browser_smoke.cjs`) — real UI over real API: 3-role login +
redirects, admin dashboard + AI health panel, all admin pages, students table,
student dashboard/exams/profile, teacher exams list, **and the full teacher
lifecycle through the UI** (create exam → code → add MCQ → schedule → publish).
Run it with `NODE_PATH` pointed at `frontend/node_modules` (puppeteer-core lives
there):

```powershell
$env:NODE_PATH = "C:\...\proooctify\frontend\node_modules"
node C:\...\browser_smoke.cjs
```

---

## Current verification status

Stage 1:
- Backend API smoke: **61/61 PASS**
- Browser UI smoke (all three roles, full teacher flow): **21/21 PASS**
- Exam lifecycle through real UI verified end-to-end (create → question → schedule → publish).

Stage 2:
- Backend end-to-end test (`test_stage2_backend.py`, temp SQLite DB):
  **58/58 PASS** — session lifecycle, readiness wizard gating, paper (no answer
  leakage), answer autosave/overwrite, heartbeat, submit + idempotent re-submit,
  grading with negative marks, window gating, timeout auto-submit (EXPIRED), and
  Stage 1 regression.
- Browser end-to-end (headless Chrome, live backend + Vite): **23/23 PASS** —
  login → My Exams → readiness wizard (identity / camera / mic / env) → start →
  4 answers + autosave + mark-for-review → simulated network loss (offline banner
  + recovery) → submit → result summary showing counts and SUBMITTED status.
- `npm run build` green (59 modules).

> Note: single benign console error (`404` favicon) — cosmetic, not an app bug.

---

Stage 3 next: the live AI proctoring pipeline (real-time frame/audio analysis,
incident detection, teacher monitoring) + AI-based reporting.
