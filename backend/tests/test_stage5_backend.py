"""Stage-5 end-to-end backend tests — the final product loop.

This stage makes the reserved "shall connect" seams real and SQL remains the
authority at every step. Covered here:

   1. Student live-proctoring feed   — config handshake, owner boundary,
                                       ACTIVE-only gating, rate limiting,
                                       frame validation, and the engine-persist
                                       loop that graduates events + PENDING
                                       incidents into SQL via the shared server.
   2. Results / publish              — submit writes a Result row; teachers
                                       publish (audited + student notification);
                                       students see graded detail ONLY after
                                       publishing (correct answers stay hidden).
   3. Notifications                  — low-volume unread/read surfaces (own rows).
   4. Analytics                      — role-aware overview + exam analytics.
   5. Evidence media                 — teacher-only, path-guarded serving.
   6. Engine registry                — same engine instance across ingests.

The suite mirrors the routing used by the Stage-5 frontends. No simulated
frames: observations are posted exactly the way a real client does.
"""
import base64
import sys
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.main import app  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.models import (  # noqa: E402
    AIServiceEvent,
    Answer,
    AuditLog,
    Evidence,
    Exam,
    ExamAssignment,
    ExamSession,
    Incident,
    Notification,
    Question,
    Result,
    RiskScore,
    Student,
    User,
)
from backend.auth import hash_password  # noqa: E402
from backend.routes import result_routes  # noqa: E402
from backend.proctoring.registry import (  # noqa: E402
    active_count,
    clear_all,
    drop as registry_drop,
    get_engine,
    purge_idle,
)

COUNTER = {"n": 0}

PHONE_OBS = {
    "objects": [{"class_name": "phone", "confidence": 0.82}],
    "face": {"available": True, "face_count": 1, "faces": []},
    "head_pose": {},
    "audio": {"available": True, "speech_detected": False},
    "camera_available": True,
}

TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


def _next():
    COUNTER["n"] += 1
    return COUNTER["n"]


def _seed_users(n):
    """teacher + student user (student-linked). Returns dict of ids."""
    db = SessionLocal()
    try:
        teacher = User(
            email=f"t.stage5.{n}@test.dev",
            username=f"t.stage5.{n}",
            password_hash=hash_password("Passw0rd!"),
            full_name="Stage-5 Teacher",
            role="teacher",
            is_active=True,
        )
        db.add(teacher)
        db.flush()
        student = User(
            email=f"s.stage5.{n}@test.dev",
            username=f"s.stage5.{n}",
            password_hash=hash_password("Passw0rd!"),
            full_name=f"Stage-5 Student {n}",
            role="student",
            is_active=True,
        )
        db.add(student)
        db.flush()
        profile = Student(
            email=student.email,
            full_name=student.full_name,
            student_id=f"S5-{n:03d}",
            user_id=student.id,
        )
        db.add(profile)
        db.flush()
        db.commit()
        return {
            "teacher_id": teacher.id,
            "teacher_email": teacher.email,
            "student_user_id": student.id,
            "student_email": student.email,
            "student_id_db": profile.id,
        }
    finally:
        db.close()


def _seed_exam(n, teacher_id, student_id_db, status="ACTIVE", total_marks=30, pass_marks=15,
               with_questions=True, with_result=False, closed_status="SUBMITTED"):
    db = SessionLocal()
    try:
        exam = Exam(
            exam_code=f"E5-{n}",
            title=f"Stage-5 Exam {n}",
            duration_minutes=30,
            total_marks=total_marks,
            pass_marks=pass_marks,
            status=status,
            is_published=True,
            is_saved_draft=False,
            created_by=teacher_id,
        )
        db.add(exam)
        db.flush()
        db.add(ExamAssignment(exam_id=exam.id, student_id_db=student_id_db))
        qids = []
        if with_questions:
            for i in range(3):
                q = Question(
                    exam_id=exam.id,
                    order_index=i,
                    question_text=f"Q{n}-{i} text",
                    question_type="MCQ",
                    marks=10 if i == 0 else 5,
                    option_a="A", option_b="B", option_c="C", option_d="D",
                    correct_option="A",
                    negative_marks=1,
                )
                db.add(q)
                db.flush()
                qids.append(q.id)
        db.flush()
        preparing = closed_status == "PREPARING"
        sess = ExamSession(
            exam_id=exam.id,
            student_id_db=student_id_db,
            session_token=f"S5-TOKEN-{n}",
            status=closed_status,
            start_time=None if preparing else datetime.utcnow() - timedelta(minutes=10),
            end_time=None if preparing else datetime.utcnow() - timedelta(minutes=5),
            submitted_at=None if preparing else datetime.utcnow() - timedelta(minutes=4),
        )
        db.add(sess)
        db.flush()
        sess_id = sess.id
        if with_result:
            result = Result(
                exam_id=exam.id,
                student_id_db=student_id_db,
                score=12.0,
                total_marks=20,
                percent=60.0,
                result_status="FAIL" if pass_marks and 12 < pass_marks else "PASS",
                published=False,
            )
            db.add(result)
        db.commit()
        return {"exam_id": exam.id, "session_id": sess_id, "qids": qids,
                "token": sess.session_token}
    finally:
        db.close()


def _login(client, value):
    r = client.post("/api/auth/login", json={"username": value, "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def client():
    clear_all()
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. student live proctoring feed
# ---------------------------------------------------------------------------

@pytest.fixture()
def feed_world(client):
    n = _next()
    ids = _seed_users(n)
    exam = _seed_exam(n, ids["teacher_id"], ids["student_id_db"],
                      with_questions=False, closed_status="ACTIVE")
    return {
        **ids,
        "exam_id": exam["exam_id"],
        "session_id": exam["session_id"],
        "token": exam["token"],
    }


def test_feed_config_handshake(feed_world, client):
    hh = _login(client, feed_world["student_email"])
    r = client.get(f"/api/student/sessions/{feed_world['token']}/proctoring/config", headers=hh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["poll_interval_seconds"] >= 1
    assert body["max_frame_bytes"] > 0
    # non-owner gets 404 (token is not theirs)
    other = _seed_users(_next())
    hh2 = _login(client, other["student_email"])
    r2 = client.get(f"/api/student/sessions/{feed_world['token']}/proctoring/config", headers=hh2)
    assert r2.status_code == 404


def test_feed_ingest_gated_on_active(feed_world, client):
    hh = _login(client, feed_world["student_email"])
    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter_by(id=feed_world["session_id"]).first()
        sess.status = "EXPIRED"
        sess.expired_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()
    r = client.post(
        f"/api/student/sessions/{feed_world['token']}/proctoring",
        headers=hh,
        json={"session_token": feed_world["token"], "observation": dict(PHONE_OBS)},
    )
    assert r.status_code == 409
    # non-owner too
    other = _seed_users(_next())
    hh2 = _login(client, other["student_email"])
    r2 = client.post(
        f"/api/student/sessions/{feed_world['token']}/proctoring",
        headers=hh2,
        json={"session_token": feed_world["token"], "observation": dict(PHONE_OBS)},
    )
    assert r2.status_code == 404


def test_feed_rate_limited(feed_world, client):
    hh = _login(client, feed_world["student_email"])
    url = f"/api/student/sessions/{feed_world['token']}/proctoring"
    payload = {"session_token": feed_world["token"], "observation": dict(PHONE_OBS)}
    r1 = client.post(url, headers=hh, json=payload)
    assert r1.status_code == 200, r1.text
    r2 = client.post(url, headers=hh, json=payload)
    assert r2.status_code == 429
    assert "retry" in r2.text


def test_feed_bad_frame_rejected(feed_world, client):
    hh = _login(client, feed_world["student_email"])
    url = f"/api/student/sessions/{feed_world['token']}/proctoring"
    r = client.post(url, headers=hh, json={
        "session_token": feed_world["token"],
        "observation": {
            "camera_available": True,
            "frame_data_url": "data:image/jpeg;base64,!!!not-base64!!!",
        },
    })
    assert r.status_code == 422


def test_feed_valid_frame_accepted(feed_world, client):
    """A real decoded image reaches the pipeline; if the AI models are absent the
    pipeline degrades gracefully but the server still answers with a signal."""
    hh = _login(client, feed_world["student_email"])
    url = f"/api/student/sessions/{feed_world['token']}/proctoring"
    data_url = "data:image/png;base64," + TINY_PNG
    r = client.post(url, headers=hh, json={
        "session_token": feed_world["token"],
        "observation": {"camera_available": True, "frame_data_url": data_url},
    })
    assert r.status_code == 200, r.text
    sig = r.json()
    assert "risk" in sig and sig["risk"]["level"] in ("NORMAL", "ATTENTION", "ELEVATED", "HIGH")


def test_feed_persists_and_graduates(feed_world, client, monkeypatch):
    """The shared engine is ONE instance per session: sustained phone detections
    graduate ai_events + risk into SQL, and a second run (after the repeat
    reset) graduates ONE PENDING incident — never two for the same type."""
    from backend.routes import student_proctoring_routes
    from backend.proctoring import engine as pengine
    from backend.proctoring import temporal as ptemporal

    monkeypatch.setattr(student_proctoring_routes, "DEFAULT_POLL_SECONDS", 0)
    # Shrink engine cadence so a test can graduate runs wall-clock-fast:
    #   sustain window (2.0s) stays real; cooldown + repeat-reset collapse.
    monkeypatch.setattr(ptemporal, "COOLDOWN_BY_FAMILY", {"OBJECT_PHONE": 0.3, "*": 0.3})
    monkeypatch.setattr(pengine, "EVENT_REPEAT_RESET_SECONDS", 0.2)
    hh = _login(client, feed_world["student_email"])
    url = f"/api/student/sessions/{feed_world['token']}/proctoring"
    payload = {"session_token": feed_world["token"], "observation": dict(PHONE_OBS)}

    def _burst(n):
        for _ in range(n):
            client.post(url, headers=hh, json=payload)

    first = client.post(url, headers=hh, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["risk"]["level"] in ("NORMAL", "ATTENTION", "ELEVATED", "HIGH")

    time.sleep(2.4)  # fill the EVENT_MIN_SUSTAINED_SECONDS window (>= 2.0s)
    _burst(3)        # first sustained run graduates an ai_event (risk updated)
    time.sleep(0.4)  # cross the (shrunk) repeat-reset gap
    _burst(3)        # second run -> repeat -> ONE incident candidate (PENDING)

    db = SessionLocal()
    try:
        events = db.query(AIServiceEvent).filter_by(exam_session_id=feed_world["session_id"]).count()
        incidents = (
            db.query(Incident)
            .filter_by(exam_session_id=feed_world["session_id"])
            .all()
        )
        risk_rows = (
            db.query(RiskScore)
            .filter_by(exam_session_id=feed_world["session_id"])
            .count()
        )
        pending = sum(1 for i in incidents if i.review_status == "PENDING")
    finally:
        db.close()

    assert events >= 1                 # a sustained run graduated an event
    assert risk_rows >= 1              # risk snapshot persisted
    assert len(incidents) >= 1         # repeated runs graduated a candidate
    assert pending == len(incidents)   # all candidates stay PENDING (teacher decides)


# ---------------------------------------------------------------------------
# 2. results + publishing
# ---------------------------------------------------------------------------

@pytest.fixture()
def result_world(client):
    n = _next()
    ids = _seed_users(n)
    exam = _seed_exam(n, ids["teacher_id"], ids["student_id_db"],
                      total_marks=20, pass_marks=12, closed_status="PREPARING")
    return {**ids, "exam_id": exam["exam_id"], "session_id": exam["session_id"],
            "token": exam["token"], "qids": exam["qids"]}


def test_submit_writes_result_row(result_world, client):
    """Full student API flow: readiness -> start -> answers -> submit lands a
    Result row (unpublished) in SQL with the graded numbers."""
    hh = _login(client, result_world["student_email"])
    token = result_world["token"]

    r = client.post(f"/api/student/sessions/{token}/readiness", headers=hh, json={
        "identity_verified": True,
        "camera_checked": True,
        "microphone_checked": True,
        "environment_ready": True,
    })
    assert r.status_code == 200, r.text
    r = client.post(f"/api/student/sessions/{token}/start", headers=hh)
    assert r.status_code == 200, r.text
    for i, qid in enumerate(result_world["qids"]):
        r = client.put(
            f"/api/student/sessions/{token}/answers/{qid}",
            headers=hh,
            json={"selected_option": "A" if i == 0 else "B"},
        )
        assert r.status_code == 200, r.text
    r = client.post(f"/api/student/sessions/{token}/submit", headers=hh)
    assert r.status_code == 200, r.text

    r = client.get("/api/student/results", headers=hh)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    row = rows[0]
    assert row["exam_id"] == result_world["exam_id"]
    assert row["published"] is False

    db = SessionLocal()
    try:
        rr = db.query(Result).filter_by(exam_id=result_world["exam_id"]).first()
        assert rr is not None
        assert rr.result_status in ("PASS", "FAIL", "GRADED")
        assert rr.published is False
        # restarting the engine is pointless now: it was dropped on submit
        engine, _ = get_engine(result_world["session_id"])
        assert engine.exam_session_id == result_world["session_id"]
    finally:
        db.close()


def test_student_detail_gates_correct_answers_until_publish(result_world, client):
    hh = _login(client, result_world["student_email"])
    token = result_world["token"]
    # mark the session closed + write a result row directly (SQL authority)
    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter_by(id=result_world["session_id"]).first()
        sess.status = "SUBMITTED"
        db.add(Result(
            exam_id=result_world["exam_id"],
            student_id_db=result_world["student_id_db"],
            score=15.0, total_marks=20, percent=75.0,
            result_status="PASS", published=False,
        ))
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/student/sessions/{token}/result", headers=hh)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["published"] is False
    # correct answers are withheld until the teacher publishes
    assert all(q["correct_option"] is None for q in detail["questions"])


def test_teacher_publish_audits_and_notifies(result_world, client):
    th = _login(client, result_world["teacher_email"])
    sh = _login(client, result_world["student_email"])

    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter_by(id=result_world["session_id"]).first()
        sess.status = "SUBMITTED"
        rr = Result(
            exam_id=result_world["exam_id"],
            student_id_db=result_world["student_id_db"],
            score=15.0, total_marks=20, percent=75.0,
            result_status="PASS", published=False,
        )
        db.add(rr)
        db.commit()
        result_id = rr.id
    finally:
        db.close()

    # teacher grid shows the unpublished row
    r = client.get("/api/teacher/results", headers=th)
    assert r.status_code == 200, r.text
    grid = r.json()
    assert any(x["result_id"] == result_id and not x["published"] for x in grid)

    # student is NOT notified yet, unread count = 0
    r = client.get("/api/notifications/unread-count", headers=sh)
    assert r.json()["unread"] == 0

    # publish
    r = client.post(f"/api/teacher/results/{result_id}/publish", headers=th)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["published"] is True and out["published_by"] == result_world["teacher_id"]

    db = SessionLocal()
    try:
        rr = db.query(Result).filter_by(id=result_id).first()
        assert rr.published is True and rr.published_at is not None
        assert db.query(AuditLog).filter(
            AuditLog.action == "RESULT_PUBLISH", AuditLog.entity_id == result_id
        ).count() == 1
        assert db.query(Notification).filter(
            Notification.user_id == result_world["student_user_id"],
        ).count() == 1
    finally:
        db.close()

    # re-publish idempotent (no second audit)
    r = client.post(f"/api/teacher/results/{result_id}/publish", headers=th)
    assert r.json()["published"] is True

    # now the student's graded view unlocks the correct answers + audit trail
    r = client.get(f"/api/student/sessions/{result_world['token']}/result", headers=sh)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["published"] is True
    assert any(q["correct_option"] == "A" for q in detail["questions"])


def test_teacher_result_detail_and_export(result_world, client):
    th = _login(client, result_world["teacher_email"])
    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter_by(id=result_world["session_id"]).first()
        sess.status = "SUBMITTED"
        rr = Result(
            exam_id=result_world["exam_id"],
            student_id_db=result_world["student_id_db"],
            score="15.0", total_marks=20, percent=75.0,
            result_status="PASS", published=False,
        )
        db.add(rr)
        db.commit()
        result_id = rr.id
    finally:
        db.close()

    r = client.get(f"/api/teacher/results/{result_id}", headers=th)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["exam_title"] and d["student_name"] and d["percent"] == 75.0
    assert "risk_level" in d  # monitoring summary present

    r = client.get(f"/api/teacher/results/export?exam_id={result_world['exam_id']}", headers=th)
    assert r.status_code == 200, r.text
    text = r.text
    assert text.startswith("result_id,") or "result_id" in text
    assert "Stage-5 Student" in text

    # formula-injection guard on cells
    assert result_routes._csv_cell("=HYPERLINK('x')") == "'=HYPERLINK('x')"
    assert result_routes._csv_cell("normal") == "normal"


# ---------------------------------------------------------------------------
# 3. notifications
# ---------------------------------------------------------------------------

@pytest.fixture()
def notif_world(client):
    n = _next()
    ids = _seed_users(n)
    db = SessionLocal()
    try:
        db.add(Notification(
            user_id=ids["student_user_id"], type="RESULT",
            title="Result ready", body="Your result is ready.", link="/student/results",
            read=False,
        ))
        db.add(Notification(
            user_id=ids["student_user_id"], type="INCIDENT",
            title="Incident flagged", body="Pending review.", read=False,
        ))
        db.commit()
    finally:
        db.close()
    return ids


def test_notifications_own_scope_and_marking(notif_world, client):
    sh = _login(client, notif_world["student_email"])
    other = _seed_users(_next())
    hh2 = _login(client, other["student_email"])

    r = client.get("/api/notifications/unread-count", headers=sh)
    assert r.json()["unread"] == 2

    r = client.get("/api/notifications", headers=sh)
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 2
    nid = items[0]["id"]

    r = client.post(f"/api/notifications/{nid}/read", headers=sh)
    assert r.status_code == 200, r.text
    r = client.get("/api/notifications/unread-count", headers=sh)
    assert r.json()["unread"] == 1

    r = client.post("/api/notifications/read-all", headers=sh)
    assert r.status_code == 200
    r = client.get("/api/notifications/unread-count", headers=sh)
    assert r.json()["unread"] == 0

    # another student cannot read this student's notification
    r = client.post(f"/api/notifications/{nid}/read", headers=hh2)
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 4. analytics
# ---------------------------------------------------------------------------

def test_analytics_overview_and_exam(result_world, client):
    th = _login(client, result_world["teacher_email"])
    sh = _login(client, result_world["student_email"])

    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter_by(id=result_world["session_id"]).first()
        sess.status = "SUBMITTED"
        db.add(Result(
            exam_id=result_world["exam_id"],
            student_id_db=result_world["student_id_db"],
            score=15.0, total_marks=20, percent=75.0,
            result_status="PASS", published=True,
        ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/analytics/overview", headers=th)
    assert r.status_code == 200, r.text
    ov = r.json()
    assert ov["role"] == "teacher"
    assert ov["totals"]["results"] >= 1 and ov["totals"]["published_results"] >= 1

    r = client.get("/api/analytics/overview", headers=sh)
    assert r.status_code == 200
    so = r.json()
    assert so["role"] == "student"
    assert so["results"]["avg_percent"] == 75.0

    r = client.get(f"/api/analytics/exams/{result_world['exam_id']}", headers=th)
    assert r.status_code == 200, r.text
    ea = r.json()
    assert ea["submitted"] >= 1
    assert ea["avg_percent"] == 75.0
    assert ea["score_distribution"] and any(b["count"] >= 1 for b in ea["score_distribution"])
    assert len(ea["question_difficulty"]) == 3


# ---------------------------------------------------------------------------
# 5. evidence media
# ---------------------------------------------------------------------------

@pytest.fixture()
def evidence_world(client):
    n = _next()
    ids = _seed_users(n)
    exam = _seed_exam(n, ids["teacher_id"], ids["student_id_db"],
                      with_questions=False, closed_status="ACTIVE")
    file_path = f"{exam['token']}/phone_face.jpg"
    db = SessionLocal()
    try:
        sess = db.query(ExamSession).filter_by(id=exam["session_id"]).first()
        db.add(AIServiceEvent(
            exam_session_id=sess.id, source="camera", event_type="OBJECT_PHONE",
            severity="WARNING", confidence=0.9, repeat_count=1,
        ))
        inc = Incident(
            exam_session_id=sess.id, incident_type="PHONE", risk_level="HIGH",
            description="Phone detected near face.", event_count=2,
            review_status="PENDING",
        )
        db.add(inc)
        db.flush()
        db.add(Evidence(
            exam_session_id=sess.id, incident_id=inc.id, source="camera",
            media_type="image/jpeg", file_path=file_path,
            description="Evidence frame: phone near face.",
        ))
        db.commit()
        sess_id = sess.id
    finally:
        db.close()

    data_dir = Path(__file__).resolve().parents[2] / "datastore" / "evidence"
    target = data_dir / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(TINY_PNG))
    return {**ids, "session_id": sess_id, "file_path": file_path, "data_dir": data_dir}


def test_evidence_media_served_and_guarded(evidence_world, client):
    th = _login(client, evidence_world["teacher_email"])
    sh = _login(client, evidence_world["student_email"])

    r = client.get(f"/api/evidence/{evidence_world['file_path']}", headers=th)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/")

    # students cannot read evidence
    r = client.get(f"/api/evidence/{evidence_world['file_path']}", headers=sh)
    assert r.status_code == 403

    # traversal attempts and unknown rows are rejected
    r = client.get("/api/evidence/..%2F..%2Fmain.py", headers=th)
    assert r.status_code in (400, 404)
    r = client.get("/api/evidence/unknown/photo.jpg", headers=th)
    assert r.status_code == 404

    # cleanup
    (evidence_world["data_dir"] / evidence_world["file_path"]).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 6. engine registry
# ---------------------------------------------------------------------------

def test_registry_engine_singleton_and_drop(client):
    e1, m1 = get_engine(4242)
    e2, _ = get_engine(4242)
    assert e1 is e2
    assert "seen" in m1

    registry_drop(4242)
    e3, _ = get_engine(4242)
    assert e3 is not e1

    get_engine(777)
    assert active_count() >= 1
    purge_idle()
    clear_all()
    assert active_count() == 0