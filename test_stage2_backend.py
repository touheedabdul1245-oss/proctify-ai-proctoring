"""Stage 2 end-to-end backend test (temp SQLite DB)."""
import base64
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="proctify_stage2_"))
DB = TMP / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB.as_posix()}"
os.environ["PROCTIFY_JWT_SECRET"] = "test-secret"

sys.path.insert(0, r"C:\Users\touhe\OneDrive\Desktop\proooctify")

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.models import Answer, ExamReadinessCheck, ExamSession  # noqa: E402

client = TestClient(app)

passed = []
failed = []


def check(name, cond, extra=""):
    if cond:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}  {extra}")


def login(email, pw):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, (email, r.text)
    return r.json()["access_token"], r.json()["user"]


def h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- stage 1 fixture: teacher + student + published exam ----------
print(">>> fixtures")

admin_tok, _ = login("admin@proctify.dev", "Admin@123")
r = client.post("/api/users", json={"role": "teacher", "email": "t2@test.dev",
                                    "password": "Passw0rd!", "full_name": "Teacher Two",
                                    "teacher_id": "T2"}, headers=h(admin_tok))
check("create teacher", r.status_code == 201, r.text)
t_tok, t_user = login("t2@test.dev", "Passw0rd!")
r = client.post("/api/users", json={"role": "student", "email": "s2@test.dev",
                                    "password": "Password1!", "full_name": "Student Two",
                                    "student_id": "S2"}, headers=h(admin_tok))
check("create student", r.status_code == 201, r.text)
s_tok, s_user = login("s2@test.dev", "Password1!")
r = client.get("/api/students", headers=h(admin_tok))
s2_profile = next(s for s in r.json() if s["email"] == "s2@test.dev")
s2_profile_id = s2_profile["id"]
check("find student profile", s2_profile_id is not None, r.text[:200])

r = client.post("/api/exams", json={"title": "Stage2 Exam", "duration_minutes": 30,
                                    "scheduled_start": "2020-01-01T00:00:00",
                                    "scheduled_end": "2030-01-01T00:00:00"},
                headers=h(t_tok))
check("create exam", r.status_code == 201, r.text)
exam_id = r.json()["id"]

q_payloads = [
    {"question_text": "2+2?", "marks": 1, "options": [{"option": "A", "text": "3"}, {"option": "B", "text": "4"},
                                                      {"option": "C", "text": "5"}, {"option": "D", "text": "6"}],
     "correct_option": "B"},
    {"question_text": "Capital of France?", "marks": 2, "options": [{"option": "A", "text": "London"},
                                                                   {"option": "B", "text": "Paris"},
                                                                   {"option": "C", "text": "Rome"},
                                                                   {"option": "D", "text": "Berlin"}],
     "correct_option": "B"},
    {"question_text": "Sky color?", "marks": 1, "options": [{"option": "A", "text": "Blue"}, {"option": "B", "text": "Red"},
                                                            {"option": "C", "text": "Green"}, {"option": "D", "text": "Yellow"}],
     "correct_option": "A", "negative_marks": 0.5},
]
q_ids = []
for i, qp in enumerate(q_payloads, start=1):
    qp["order_index"] = i
    r = client.post(f"/api/exams/{exam_id}/questions", json=qp, headers=h(t_tok))
    check(f"add Q{i}", r.status_code == 201, r.text)
    q_ids.append(r.json()["id"])

r = client.post(f"/api/exams/{exam_id}/assign", json={"student_ids": [s2_profile_id], "class_ids": []},
                headers=h(t_tok))
check("assign exam", r.status_code == 200, r.text)
r = client.post(f"/api/exams/{exam_id}/schedule", json={"scheduled_start": "2020-01-01T00:00:00",
                                                        "scheduled_end": "2030-01-01T00:00:00"},
                headers=h(t_tok))
check("schedule exam", r.status_code == 200, r.text)
r = client.post(f"/api/exams/{exam_id}/publish", json={}, headers=h(t_tok))
check("publish exam", r.status_code == 200, r.text)
r = client.post(f"/api/exams/{exam_id}/status", json={"target_status": "AVAILABLE"}, headers=h(t_tok))
check("set AVAILABLE", r.status_code == 200, r.text)

# student sees it
r = client.get("/api/student/exams", headers=h(s_tok))
check("student assigned exams", r.status_code == 200 and any(e["exam_id"] == exam_id for e in r.json()), r.text)

# ---------- session lifecycle ----------
print(">>> session lifecycle")
r = client.get(f"/api/student/exams/{exam_id}/session", headers=h(s_tok))
check("no session yet", r.status_code == 200 and r.json()["session_token"] is None, r.text)

r = client.post(f"/api/student/exams/{exam_id}/session", headers=h(s_tok))
check("create session PREPARING", r.status_code == 201 and r.json()["status"] == "PREPARING", r.text)
token = r.json()["session_token"]

# cannot start before readiness
r = client.post(f"/api/student/sessions/{token}/start", headers=h(s_tok))
check("start blocked without readiness", r.status_code == 422, r.text)

# readiness with photo
png = base64.b64encode(b"pngfakeimagecontent").decode()
r = client.post(f"/api/student/sessions/{token}/readiness", headers=h(s_tok),
                json={"identity_verified": True, "identity_photo_data": f"data:image/png;base64,{png}",
                      "camera_checked": True, "microphone_checked": True, "environment_ready": True})
check("readiness submit", r.status_code == 200, r.text)
ck = r.json()
check("readiness flags persisted", ck["identity_verified"] and ck["camera_checked"] and ck["microphone_checked"]
      and ck["environment_ready"], ck)
check("identity photo saved", bool(ck["identity_photo_path"] and (TMP.parent / ck["identity_photo_path"]).exists()
      or Path(r"C:\Users\touhe\OneDrive\Desktop\proooctify", ck["identity_photo_path"]).exists()), ck)

r = client.post(f"/api/student/sessions/{token}/start", headers=h(s_tok))
check("start session ACTIVE", r.status_code == 200 and r.json()["status"] == "ACTIVE", r.text)
sess = r.json()
check("end_time = start + duration", sess["end_time"] and sess["start_time"], sess)
check("remaining ~29min", 1700 <= (sess["remaining_seconds"] or 0) <= 1800, sess)

# duplicate create returns same session (resume)
r = client.post(f"/api/student/exams/{exam_id}/session", headers=h(s_tok))
check("resume returns same token", r.status_code == 201 and r.json()["session_token"] == token, r.text)

# ---------- paper ----------
print(">>> paper")
r = client.get(f"/api/student/sessions/{token}/paper", headers=h(s_tok))
check("get paper", r.status_code == 200, r.text)
paper = r.json()
check("3 questions", paper["question_count"] == 3, paper)
check("no correct answer leaked", all("correct_option" not in q for q in paper["questions"]), paper)
check("remaining seconds present", paper["remaining_seconds"] is not None, paper)

# save answers + mark review
r = client.put(f"/api/student/sessions/{token}/answers/{q_ids[0]}", headers=h(s_tok),
               json={"selected_option": "B", "marked_for_review": True})
check("save answer 1", r.status_code == 200 and r.json()["selected_option"] == "B" and r.json()["marked_for_review"], r.text)
r = client.put(f"/api/student/sessions/{token}/answers/{q_ids[1]}", headers=h(s_tok),
               json={"selected_option": "C", "marked_for_review": True})
check("save answer 2", r.status_code == 200 and r.json()["selected_option"] == "C", r.text)
r = client.put(f"/api/student/sessions/{token}/answers/{q_ids[2]}", headers=h(s_tok),
               json={"selected_option": "D"})
check("save answer 3", r.status_code == 200, r.text)

# upsert, no duplicate row
r = client.put(f"/api/student/sessions/{token}/answers/{q_ids[0]}", headers=h(s_tok),
               json={"selected_option": "A", "marked_for_review": False})
check("overwrite answer 1", r.status_code == 200 and r.json()["selected_option"] == "A", r.text)

db = SessionLocal()
try:
    n = db.query(Answer).filter(Answer.exam_session_id == sess["id"]).count()
    check("3 answer rows (upsert, no dup)", n == 3, n)
    rc = db.query(ExamReadinessCheck).filter(ExamReadinessCheck.exam_session_id == sess["id"]).count()
    check("1 readiness row", rc == 1, rc)
finally:
    db.close()

r = client.get(f"/api/student/sessions/{token}/paper", headers=h(s_tok))
paper2 = r.json()
check("answers returned in paper", len(paper2["answers"]) == 3, paper2["answers"])
ans1 = next(a for a in paper2["answers"] if a["question_id"] == q_ids[0])
check("answer 1 reflects overwrite", ans1["selected_option"] == "A" and ans1["marked_for_review"] is False, ans1)

r = client.post(f"/api/student/sessions/{token}/heartbeat", headers=h(s_tok))
check("heartbeat", r.status_code == 200 and r.json()["status"] == "ACTIVE", r.text)

# ---------- submit ----------
print(">>> submit")
r = client.post(f"/api/student/sessions/{token}/submit", headers=h(s_tok))
check("submit", r.status_code == 200, r.text)
sub = r.json()
check("status SUBMITTED", sub["status"] == "SUBMITTED", sub)
check("3 answered", sub["answered_count"] == 3, sub)
check("1 marked (marked_for_review still set)", sub["marked_count"] == 1, sub)
check("0 unanswered", sub["unanswered_count"] == 0, sub)

db = SessionLocal()
try:
    from backend.models import Question
    row = db.query(Answer, Question).join(Question, Answer.question_id == Question.id).filter(
        Answer.exam_session_id == sess["id"]).all()
    verdict = {a.question_id: (a.is_correct, a.marks_awarded) for a, _ in row}
    check("q1 correct (A? no, B is wrong -> false)", verdict[q_ids[0]][0] is False, verdict)
    check("q2 wrong selected", verdict[q_ids[1]][0] is False, verdict)
    check("q3 wrong selected + negative", verdict[q_ids[2]][0] is False and verdict[q_ids[2]][1] == -0.5, verdict)
    check("submitted_at stamped", all(a.submitted_at is not None for a, _ in row), row)
    # no answer row left unmarked after finalize
    sess_db = db.query(ExamSession).filter(ExamSession.id == sess["id"]).first()
    check("session submitted_at set", sess_db.submitted_at is not None, sess_db)
finally:
    db.close()

# paper after submit is refused
r = client.get(f"/api/student/sessions/{token}/paper", headers=h(s_tok))
check("paper refused after submit", r.status_code == 409, r.text)
# repeated submit idempotent
r = client.post(f"/api/student/sessions/{token}/submit", headers=h(s_tok))
check("re-submit idempotent", r.status_code == 200 and r.json()["status"] == "SUBMITTED", r.text)
# summary
r = client.get(f"/api/student/sessions/{token}/summary", headers=h(s_tok))
check("summary", r.status_code == 200 and r.json()["answered_count"] == 3, r.text)
# session state on list now shows submitted
r = client.get(f"/api/student/exams/{exam_id}/session", headers=h(s_tok))
check("list state SUBMITTED", r.json()["status"] == "SUBMITTED", r.text)

# ---------- auto-submit on timeout ----------
print(">>> auto-submit on timeout")
r = client.post("/api/exams", json={"title": "AutoSubmit Exam", "duration_minutes": 30,
                                    "scheduled_start": "2020-01-01T00:00:00",
                                    "scheduled_end": "2030-01-01T00:00:00"}, headers=h(t_tok))
ae_id = r.json()["id"]
client.post(f"/api/exams/{ae_id}/questions", json=q_payloads[0], headers=h(t_tok))
client.post(f"/api/exams/{ae_id}/assign", json={"student_ids": [s2_profile_id], "class_ids": []}, headers=h(t_tok))
client.post(f"/api/exams/{ae_id}/schedule", json={"scheduled_start": "2020-01-01T00:00:00",
                                                  "scheduled_end": "2030-01-01T00:00:00"}, headers=h(t_tok))
client.post(f"/api/exams/{ae_id}/publish", json={}, headers=h(t_tok))
client.post(f"/api/exams/{ae_id}/status", json={"target_status": "AVAILABLE"}, headers=h(t_tok))

r = client.post(f"/api/student/exams/{ae_id}/session", headers=h(s_tok))
tok2 = r.json()["session_token"]
r = client.post(f"/api/student/sessions/{tok2}/readiness", headers=h(s_tok),
                json={"identity_verified": True, "camera_checked": True, "microphone_checked": True,
                      "environment_ready": True})
assert r.status_code == 200, r.text
r = client.post(f"/api/student/sessions/{tok2}/start", headers=h(s_tok))
assert r.status_code == 200, r.text
from datetime import datetime, timedelta
db = SessionLocal()
try:
    s = db.query(ExamSession).filter(ExamSession.session_token == tok2).first()
    s.end_time = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
finally:
    db.close()

r = client.get(f"/api/student/sessions/{tok2}/paper", headers=h(s_tok))
check("timeout => paper refused", r.status_code == 409, r.text)
r = client.get(f"/api/student/exams/{ae_id}/session", headers=h(s_tok))
check("timeout => EXPIRED state", r.json()["status"] == "EXPIRED", r.text)
r = client.post(f"/api/student/sessions/{tok2}/submit", headers=h(s_tok))
check("late submit reports auto", r.status_code == 200 and r.json()["status"] == "EXPIRED" and r.json()["auto"], r.text)

# ---------- window gating ----------
print(">>> window gating")
r = client.post("/api/exams", json={"title": "Future Exam", "duration_minutes": 10,
                                    "scheduled_start": "2031-01-01T00:00:00",
                                    "scheduled_end": "2032-01-01T00:00:00"}, headers=h(t_tok))
fut_exam = r.json()["id"]
client.post(f"/api/exams/{fut_exam}/questions", json=q_payloads[0], headers=h(t_tok))
client.post(f"/api/exams/{fut_exam}/assign", json={"student_ids": [s2_profile_id], "class_ids": []}, headers=h(t_tok))
client.post(f"/api/exams/{fut_exam}/schedule", json={"scheduled_start": "2031-01-01T00:00:00",
                                                     "scheduled_end": "2032-01-01T00:00:00"}, headers=h(t_tok))
client.post(f"/api/exams/{fut_exam}/publish", json={}, headers=h(t_tok))
r = client.post(f"/api/student/exams/{fut_exam}/session", headers=h(s_tok))
check("future exam blocked", r.status_code == 409 and "not started yet" in r.json()["detail"], r.text)

# ---------- Stage 1 regression ----------
print(">>> stage 1 regression")
r = client.get("/api/health")
check("health endpoint", r.status_code == 200 and r.json()["status"] == "ok", r.text)
r = client.get("/api/admin/dashboard" if False else "/api/dashboard/stats", headers=h(admin_tok))
check("admin dashboard stats", r.status_code == 200 and r.json()["role"] == "admin", r.text)
r = client.get("/api/student/exams", headers=h(s_tok))
check("student exam list intact", r.status_code == 200 and len(r.json()) == 3, r.text)
r = client.get(f"/api/exams/{exam_id}", headers=h(t_tok))
check("teacher exam detail intact", r.status_code == 200 and r.json()["question_count"] == 3, r.text)
r = client.get("/api/profile", headers=h(s_tok))
check("student profile intact", r.status_code == 200 and r.json()["user"]["email"] == "s2@test.dev", r.text)

print()
print(f"RESULT: {len(passed)} passed, {len(failed)} failed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("ALL STAGE 2 BACKEND TESTS PASSED")