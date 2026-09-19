"""Stage-7 backend tests — authoritative exam state machine, scheduling,
termination, validation, bulk-assignment summary and the teacher live list.

SQL is the source of truth and the backend clock drives the window:

   DRAFT -> SCHEDULED -> AVAILABLE -> ACTIVE -> COMPLETED
   plus   DRAFT/SCHEDULED/AVAILABLE -> CANCELLED
   plus   AVAILABLE/ACTIVE -> TERMINATED (answers preserved, no grading)

The frontend never decides openness via its own timer; every test below
verifies the server/DB semantics through the real HTTP surface.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.main import app  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.models import (  # noqa: E402
    Answer,
    Exam,
    ExamAssignment,
    ExamSession,
    Question,
    Result,
    Student,
    Teacher,
    User,
)
from backend.auth import hash_password  # noqa: E402

COUNTER = {"n": 0}


def _next():
    COUNTER["n"] += 1
    return COUNTER["n"]


def _seed_world(n):
    """teacher (with Teacher profile) + student (with Student profile)."""
    db = SessionLocal()
    try:
        teacher_user = User(
            email=f"t.st7.{n}@test.dev",
            username=f"t.st7.{n}",
            password_hash=hash_password("Passw0rd!"),
            full_name="Stage-7 Teacher",
            role="teacher",
            is_active=True,
        )
        db.add(teacher_user)
        db.flush()
        teacher = Teacher(teacher_id=f"T7-{n:03d}", user_id=teacher_user.id, email=teacher_user.email, full_name=teacher_user.full_name)
        db.add(teacher)
        db.flush()

        student_user = User(
            email=f"s.st7.{n}@test.dev",
            username=f"s.st7.{n}",
            password_hash=hash_password("Passw0rd!"),
            full_name=f"Stage-7 Student {n}",
            role="student",
            is_active=True,
        )
        db.add(student_user)
        db.flush()
        profile = Student(
            email=student_user.email,
            full_name=student_user.full_name,
            student_id=f"S7-{n:03d}",
            user_id=student_user.id,
        )
        db.add(profile)
        db.flush()
        db.commit()
        return {
            "teacher_id": teacher.id,
            "teacher_user_id": teacher_user.id,
            "teacher_email": teacher_user.email,
            "student_db_id": profile.id,
            "student_user_id": student_user.id,
            "student_email": student_user.email,
        }
    finally:
        db.close()


def _login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def client():
    return TestClient(app)


def _create_exam(client, th, **over):
    base = datetime.utcnow()
    payload = {
        "title": f"St7 Exam {_next()}",
        "description": "state machine test",
        "subject": "IS",
        "duration_minutes": 30,
        "total_marks": 10,
        "pass_marks": 1,
        "scheduled_start": (base + timedelta(hours=1)).isoformat(),
        "scheduled_end": (base + timedelta(hours=2)).isoformat(),
        "save_as_draft": False,
    }
    if "scheduled_start" in over and isinstance(over["scheduled_start"], datetime):
        over["scheduled_start"] = over["scheduled_start"].isoformat()
    if "scheduled_end" in over and isinstance(over["scheduled_end"], datetime):
        over["scheduled_end"] = over["scheduled_end"].isoformat()
    payload.update(over)
    r = client.post("/api/exams", json=payload, headers=th)
    assert r.status_code == 201, r.text
    return r.json()


def _add_question(client, th, exam_id, **over):
    payload = {
        "question_text": "What is the capital of France?",
        "order_index": 0,
        "marks": 2,
        "options": [
            {"option": "A", "text": "Paris"},
            {"option": "B", "text": "Rome"},
            {"option": "C", "text": "Madrid"},
            {"option": "D", "text": "Berlin"},
        ],
        "correct_option": "A",
        "negative_marks": 0.5,
    }
    payload.update(over)
    r = client.post(f"/api/exams/{exam_id}/questions", json=payload, headers=th)
    assert r.status_code == 201, r.text
    return r.json()


def _schedule(client, th, exam_id, start=None, end=None):
    base = datetime.utcnow()
    start = start or (base + timedelta(hours=1))
    end = end or (start + timedelta(hours=1))
    r = client.post(
        f"/api/exams/{exam_id}/schedule",
        json={"scheduled_start": start.isoformat(), "scheduled_end": end.isoformat()},
        headers=th,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _open_exam(client, th, start=None):
    """Create + questions + schedule + publish in one go (status SCHEDULED);
    reads reconcile it to AVAILABLE once the window has opened."""
    exam = _create_exam(client, th)
    _add_question(client, th, exam["id"])
    _schedule(client, th, exam["id"], start=start)
    _publish(client, th, exam["id"])
    return exam


def _publish(client, th, exam_id):
    r = client.post(f"/api/exams/{exam_id}/publish", headers=th)
    assert r.status_code == 200, r.text
    return r.json()


def _get(client, th, exam_id):
    r = client.get(f"/api/exams/{exam_id}", headers=th)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------


def test_draft_scheduled_then_window_drives_available_then_completed(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)
    assert exam["status"] == "DRAFT"

    scheduled = _schedule(client, th, exam["id"])
    assert scheduled["status"] == "SCHEDULED"
    _add_question(client, th, exam["id"])
    published = _publish(client, th, exam["id"])
    assert published["status"] == "SCHEDULED" and published["is_published"] is True

    # move window into the past -> reconcile on read flips to AVAILABLE
    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.scheduled_start = datetime.utcnow() - timedelta(minutes=5)
        row.scheduled_end = datetime.utcnow() + timedelta(hours=2)
        db.commit()
    finally:
        db.close()
    assert _get(client, th, exam["id"])["status"] == "AVAILABLE"

    # move end into the past -> COMPLETED
    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.scheduled_end = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert _get(client, th, exam["id"])["status"] == "COMPLETED"


def test_before_window_pulls_available_back_to_scheduled(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th)

    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.status = "AVAILABLE"
        row.scheduled_start = datetime.utcnow() + timedelta(days=1)
        row.scheduled_end = datetime.utcnow() + timedelta(days=2)
        db.commit()
    finally:
        db.close()
    assert _get(client, th, exam["id"])["status"] == "SCHEDULED"


def test_terminal_states_are_frozen_by_clock(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th)

    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.status = "TERMINATED"
        row.scheduled_start = datetime.utcnow() - timedelta(days=1)
        row.scheduled_end = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    assert _get(client, th, exam["id"])["status"] == "TERMINATED"

    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.status = "CANCELLED"
        row.scheduled_start = datetime.utcnow() - timedelta(days=1)
        row.scheduled_end = datetime.utcnow() + timedelta(days=1)
        db.commit()
    finally:
        db.close()
    assert _get(client, th, exam["id"])["status"] == "CANCELLED"


def test_cancel_is_cancelled_not_archived(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)
    r = client.post(f"/api/exams/{exam['id']}/cancel", headers=th)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "CANCELLED" and body["is_published"] is False


def test_cancel_blocked_on_active(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th)
    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.status = "ACTIVE"
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/exams/{exam['id']}/cancel", headers=th)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# termination
# ---------------------------------------------------------------------------


def test_terminate_persists_terminated_and_preserves_answers(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th, start=datetime.utcnow() - timedelta(minutes=5))
    q = _add_question(client, th, exam["id"])
    _id = exam["id"]

    db = SessionLocal()
    try:
        db.add(ExamAssignment(exam_id=_id, student_id_db=w["student_db_id"]))
        sess = ExamSession(
            exam_id=_id,
            student_id_db=w["student_db_id"],
            session_token=f"st7-term-{_next()}",
            status="ACTIVE",
            start_time=datetime.utcnow() - timedelta(minutes=2),
            end_time=datetime.utcnow() + timedelta(minutes=28),
        )
        db.add(sess)
        db.flush()
        db.add(Answer(exam_session_id=sess.id, question_id=q["id"], selected_option="A"))
        db.commit()
        session_id = sess.id
    finally:
        db.close()

    r = client.post(f"/api/exams/{_id}/terminate", headers=th)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "TERMINATED"

    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        assert sess.status == "TERMINATED"
        answers = db.query(Answer).filter(Answer.exam_session_id == session_id).all()
        assert len(answers) == 1 and answers[0].selected_option == "A"
        # termination must NOT auto-grade: no Result row exists
        assert db.query(Result).filter(Result.exam_id == _id).count() == 0
        row = db.query(Exam).filter(Exam.id == _id).first()
        assert row.status == "TERMINATED"
    finally:
        db.close()


def test_terminate_requires_live_exam(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)
    r = client.post(f"/api/exams/{exam['id']}/terminate", headers=th)
    assert r.status_code == 422  # DRAFT cannot be terminated


def test_terminate_requires_owning_teacher(client):
    w1 = _seed_world(_next())
    w2 = _seed_world(_next())
    th1 = _login(client, w1["teacher_email"])
    th2 = _login(client, w2["teacher_email"])
    exam = _open_exam(client, th1, start=datetime.utcnow() - timedelta(minutes=5))
    r = client.post(f"/api/exams/{exam['id']}/terminate", headers=th2)
    assert r.status_code == 403


def test_terminated_session_summary_for_student(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th, start=datetime.utcnow() - timedelta(minutes=5))
    _id = exam["id"]

    db = SessionLocal()
    try:
        db.add(ExamAssignment(exam_id=_id, student_id_db=w["student_db_id"]))
        sess = ExamSession(
            exam_id=_id,
            student_id_db=w["student_db_id"],
            session_token=f"st7-sum-{_next()}",
            status="ACTIVE",
            start_time=datetime.utcnow() - timedelta(minutes=2),
            end_time=datetime.utcnow() + timedelta(minutes=28),
        )
        db.add(sess)
        db.commit()
        token = sess.session_token
    finally:
        db.close()

    client.post(f"/api/exams/{_id}/terminate", headers=th)

    sh = _login(client, w["student_email"])
    r = client.post(f"/api/student/sessions/{token}/submit", headers=sh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "TERMINATED"
    assert "terminated" in body["message"].lower()
    assert body["auto"] is False


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_question_validation_rules(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)

    def base(over):
        p = {
            "question_text": "Q?",
            "order_index": 0,
            "marks": 1,
            "options": [{"option": "A", "text": "x"}, {"option": "B", "text": "y"}],
            "correct_option": "A",
            "negative_marks": 0,
        }
        p.update(over)
        return client.post(f"/api/exams/{exam['id']}/questions", json=p, headers=th)

    assert base({"marks": 0}).status_code == 422
    assert base({"negative_marks": -1.0}).status_code == 422
    assert base({"question_text": "   "}).status_code == 422
    assert base({"options": [{"option": "A", "text": "only one"}]}).status_code == 422
    assert base({"options": [{"option": "A", "text": "x"}, {"option": "B", "text": ""}]}).status_code == 422
    assert base({"correct_option": "C"}).status_code == 422  # not among provided options
    assert base({"options": [{"option": "E", "text": "bad"}, {"option": "A", "text": "x"}]}).status_code == 422


def test_publish_requires_questions_schedule_and_pass_marks(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)

    # no questions yet -> publish 422
    r = client.post(f"/api/exams/{exam['id']}/publish", headers=th)
    assert r.status_code == 422 and "question" in r.json()["detail"].lower()

    _add_question(client, th, exam["id"])

    # no schedule yet -> publish 422 (create an unscheduled exam)
    unscheduled = _create_exam(client, th, scheduled_start=None, scheduled_end=None)
    _add_question(client, th, unscheduled["id"])
    r = client.post(f"/api/exams/{unscheduled['id']}/publish", headers=th)
    assert r.status_code == 422 and "Schedule" in r.json()["detail"]

    # pass_marks > total -> publish 422
    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.pass_marks = 50
        row.total_marks = 10
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/exams/{exam['id']}/publish", headers=th)
    assert r.status_code == 422 and "Passing marks" in r.json()["detail"]
    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == exam["id"]).first()
        row.pass_marks = 1
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/exams/{exam['id']}/publish", headers=th)
    assert r.status_code == 200, r.text


def test_schedule_rejects_inverted_window(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)
    r = client.post(
        f"/api/exams/{exam['id']}/schedule",
        json={
            "scheduled_start": datetime.utcnow().isoformat(),
            "scheduled_end": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        },
        headers=th,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# bulk assignment summary
# ---------------------------------------------------------------------------


def test_assign_returns_summary_with_invalid_and_duplicates(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)
    _id = exam["id"]

    db = SessionLocal()
    try:
        db.add(ExamAssignment(exam_id=_id, student_id_db=w["student_db_id"]))
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/exams/{_id}/assign",
        json={"student_ids": [w["student_db_id"], w["student_db_id"], 999999], "class_ids": []},
        headers=th,
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["assignment_summary"]["added_students"] == 0
    assert detail["assignment_summary"]["duplicate_students"] == 2  # two re-requests of the same already-assigned student
    assert detail["assignment_summary"]["invalid_students"] == 1
    assert detail["assigned_student_count"] == 1


def test_assign_adds_missing_students(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _create_exam(client, th)
    _id = exam["id"]
    r = client.post(
        f"/api/exams/{_id}/assign",
        json={"student_ids": [w["student_db_id"]], "class_ids": []},
        headers=th,
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["assignment_summary"]["added_students"] == 1
    assert detail["assigned_student_count"] == 1


# ---------------------------------------------------------------------------
# window gating for students + auto-finalize on window close
# ---------------------------------------------------------------------------


def test_session_gated_outside_window(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th, start=datetime.utcnow() + timedelta(hours=2))
    _id = exam["id"]

    db = SessionLocal()
    try:
        db.add(ExamAssignment(exam_id=_id, student_id_db=w["student_db_id"]))
        db.commit()
    finally:
        db.close()

    sh = _login(client, w["student_email"])
    r = client.post(f"/api/student/exams/{_id}/session", headers=sh)
    assert r.status_code == 409  # scheduled but not yet started
    assert r.json()["detail"] == "Exam has not started yet"

    # now past the end: COMPLETED, still not taker-open
    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == _id).first()
        row.scheduled_start = datetime.utcnow() - timedelta(hours=3)
        row.scheduled_end = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/student/exams/{_id}/session", headers=sh)
    assert r.status_code == 409
    # reconcile already closed the exam as COMPLETED by the clock
    assert r.json()["detail"] == "Exam is not open for taking (status COMPLETED)"


def test_window_close_auto_finalizes_active_sessions(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th, start=datetime.utcnow() - timedelta(hours=3))
    q = _add_question(client, th, exam["id"])
    _id = exam["id"]

    db = SessionLocal()
    try:
        db.add(ExamAssignment(exam_id=_id, student_id_db=w["student_db_id"]))
        sess = ExamSession(
            exam_id=_id,
            student_id_db=w["student_db_id"],
            session_token=f"st7-exp-{_next()}",
            status="ACTIVE",
            start_time=datetime.utcnow() - timedelta(hours=2),
            end_time=datetime.utcnow() - timedelta(minutes=30),
        )
        db.add(sess)
        db.flush()
        db.add(Answer(exam_session_id=sess.id, question_id=q["id"], selected_option="A"))
        db.commit()
        session_id = sess.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        row = db.query(Exam).filter(Exam.id == _id).first()
        row.scheduled_end = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    detail = _get(client, th, _id)
    assert detail["status"] == "COMPLETED"

    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        assert sess.status == "EXPIRED"
        assert db.query(Result).filter(Result.exam_id == _id).count() == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# teacher live list (dashboard)
# ---------------------------------------------------------------------------


def test_live_students_list_is_assignment_based(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th, start=datetime.utcnow() - timedelta(minutes=5))
    _id = exam["id"]

    db = SessionLocal()
    try:
        db.add(ExamAssignment(exam_id=_id, student_id_db=w["student_db_id"]))
        sess = ExamSession(
            exam_id=_id,
            student_id_db=w["student_db_id"],
            session_token=f"st7-live-{_next()}",
            status="ACTIVE",
            start_time=datetime.utcnow() - timedelta(minutes=1),
            end_time=datetime.utcnow() + timedelta(minutes=29),
            last_activity_at=datetime.utcnow(),
        )
        db.add(sess)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/proctoring/monitor/live-students", headers=th)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exams"] == 1
    assert body["students"] == 1
    assert body["in_progress_count"] == 1
    row = body["rows"][0]
    assert row["status"] == "ACTIVE"
    assert row["student_name"].startswith("Stage-7 Student")
    # no AI events yet -> session is ACTIVE but never "LIVE"
    assert row["monitor_status"] == "ACTIVE"
    assert body["live_count"] == 0


def test_live_list_monitor_live_only_with_events(client):
    w = _seed_world(_next())
    th = _login(client, w["teacher_email"])
    exam = _open_exam(client, th, start=datetime.utcnow() - timedelta(minutes=5))
    _id = exam["id"]
    _add_question(client, th, exam["id"])

    db = SessionLocal()
    try:
        db.add(ExamAssignment(exam_id=_id, student_id_db=w["student_db_id"]))
        sess = ExamSession(
            exam_id=_id,
            student_id_db=w["student_db_id"],
            session_token=f"st7-lv2-{_next()}",
            status="ACTIVE",
            start_time=datetime.utcnow() - timedelta(minutes=1),
            end_time=datetime.utcnow() + timedelta(minutes=29),
        )
        db.add(sess)
        db.flush()
        from backend.models import AIServiceEvent  # noqa: F401
        db.add(AIServiceEvent(
            exam_session_id=sess.id,
            event_type="CAMERA_UNAVAILABLE",
            source="client",
            severity="info",
            confidence=0.0,
            occurred_at=datetime.utcnow(),
        ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/proctoring/monitor/live-students", headers=th)
    assert r.status_code == 200, r.text
    row = [x for x in r.json()["rows"] if x["exam_id"] == _id][0]
    assert row["status"] == "ACTIVE"
    assert row["monitor_status"] == "LIVE"
    assert row["event_count_24h"] >= 1

    # once the exam is terminated, that row can never be LIVE again
    client.post(f"/api/exams/{_id}/terminate", headers=th)
    r2 = client.get("/api/proctoring/monitor/live-students", headers=th)
    row2 = [x for x in r2.json()["rows"] if x["exam_id"] == _id][0]
    assert row2["exam_status"] == "TERMINATED"
    assert row2["status"] == "TERMINATED"
    assert row2["monitor_status"] == "DONE"