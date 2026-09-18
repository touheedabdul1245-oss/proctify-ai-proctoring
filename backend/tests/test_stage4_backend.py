"""Stage-4 end-to-end backend tests — teacher monitoring dashboard.

SQL is authoritative (always). The harness mirrors test_stage2_backend.py
(proven white path): temp SQLite -> DATABASE_URL -> create_all (bootstrap) ->
TestClient -> teacher login. The monitor handshake is the SAME one the
Stage-4 frontend uses:

    1. teacher login (teacher-only surface, SQL-backed auth)
    2. seed student exam sessions + a real PENDING incident + evidence
    3. GET  /api/proctoring/monitor/overview        -> student grid + summary
    4. GET  /api/proctoring/monitor/sessions/{id}   -> risk history / timeline /
                                                        evidence cards
    5. POST /api/proctoring/monitor/ingest          -> Stage-3 pure signal is
                                                        persisted to SQL and the
                                                        grid/detail go live
    6. POST /api/proctoring/monitor/review          -> human verdict persisted
                                                        (CONFIRM / DISMISS /
                                                        RESOLVE) + audited
    7. GET  overview/detail again                   -> verdicts reflected

The review verdict is ALWAYS teacher-initiated and ALWAYS SQL-persisted; the
engine never auto-verdicts (Stage-3 proof, unchanged — incidents are created
PENDING and only the review route writes the human decision).
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.main import app  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.models import (  # noqa: E402
    AIServiceEvent,
    AuditLog,
    Evidence,
    Exam,
    ExamSession,
    Incident,
    RiskScore,
    Student,
    User,
)
from backend.auth import hash_password  # noqa: E402

COUNTER = {"n": 0}


def _next():
    COUNTER["n"] += 1
    return COUNTER["n"]


def _seed_world():
    """Idempotent-per-test seed. Returns (teacher_user_id, session_id, incident_id)."""
    n = _next()
    db = SessionLocal()
    try:
        teacher = User(
            email=f"t.stage4.{n}@test.dev",
            password_hash=hash_password("Passw0rd!"),
            full_name="Stage-4 Teacher",
            role="teacher",
            is_active=True,
        )
        db.add(teacher)
        db.flush()
        student = Student(
            email=f"s.stage4.{n}@test.dev",
            full_name=f"Stage-4 Student {n}",
            student_id=f"S4-{n:03d}",
            user_id=teacher.id,
        )
        db.add(student)
        db.flush()
        exam = Exam(
            exam_code=f"E4-{n}",
            title=f"Stage-4 Monitor Exam {n}",
            duration_minutes=30,
            total_marks=50,
            status="ACTIVE",
            is_published=True,
            is_saved_draft=False,
            created_by=teacher.id,
        )
        db.add(exam)
        db.flush()
        sess = ExamSession(
            exam_id=exam.id,
            student_id_db=student.id,
            session_token=f"S4-TOKEN-{n}",
            status="ACTIVE",
        )
        db.add(sess)
        db.flush()
        inc = Incident(
            exam_session_id=sess.id,
            incident_type="PHONE",
            risk_level="HIGH",
            confidence=0.9,
            description="Phone observed near face repeatedly.",
            event_count=3,
            event_types="OBJECT_PHONE,REPEAT_PHONE",
            resolved=False,
            review_status="PENDING",
        )
        db.add(inc)
        db.flush()
        db.add(
            Evidence(
                exam_session_id=sess.id,
                incident_id=inc.id,
                source="camera",
                media_type="image/jpeg",
                file_path=f"/evidence/{n}/phone_face.jpg",
                description=f"Evidence frame {n}: phone near face.",
            )
        )
        db.add(
            RiskScore(
                exam_session_id=sess.id,
                level="ELEVATED",
                index_value=0.62,
                score=0.62,
                reason="Sustained phone detections.",
            )
        )
        db.add(
            AIServiceEvent(
                exam_session_id=sess.id,
                source="camera",
                event_type="OBJECT_PHONE",
                severity="WARNING",
                confidence=0.92,
                repeat_count=2,
                payload=None,
            )
        )
        db.commit()
        return teacher.id, sess.id, inc.id
    finally:
        db.close()


@pytest.fixture()
def teacher_headers():
    """Login teacher on a freshly seeded world; return (headers, ids)."""
    ids = _seed_world()
    client = TestClient(app)
    r = client.post(
        "/api/auth/login",
        json={"email": f"t.stage4.{COUNTER['n']}@test.dev", "password": "Passw0rd!"},
    )
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, ids


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# overview: active student/session grid
# ---------------------------------------------------------------------------


def test_overview_grid_and_summary(client, teacher_headers):
    hh, (_, sess_id, inc_id) = teacher_headers
    r = client.get("/api/proctoring/monitor/overview", headers=hh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("sessions"), list) and len(body["sessions"]) >= 1
    row = body["sessions"][0]
    # session identity + student name/session info
    assert row["id"] == sess_id
    assert row["exam_session_id"] == sess_id
    assert row["session_token"]
    assert row["student_name"]
    assert row["student_email"]
    assert row["exam_code"]
    # risk state
    assert row["risk_level"] == "ELEVATED"
    assert round(row["risk_index"], 1) == 0.6
    # monitoring status + live signal (seeded event)
    assert row["monitor_status"] == "LIVE"
    assert row["event_count_24h"] >= 1
    # active incident count
    assert row["pending_incidents"] == 1
    assert row["incident_count"] >= 1
    assert row["evidence_count"] >= 1
    # summary counters
    assert body["total_sessions"] >= 1
    assert body["live_count"] >= 1
    assert body["pending_total"] >= 1
    assert "levels" in (body.get("contract") or {})


# ---------------------------------------------------------------------------
# detail: student detailed monitoring view
# ---------------------------------------------------------------------------


def test_detail_risk_history_timeline_evidence(client, teacher_headers):
    hh, (_, sess_id, inc_id) = teacher_headers
    r = client.get(f"/api/proctoring/monitor/sessions/{sess_id}", headers=hh)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["student_name"]
    assert d["exam_title"]
    # risk history
    assert isinstance(d.get("risk_rows"), list) and len(d["risk_rows"]) == 1
    assert d["risk_rows"][0]["level"] == "ELEVATED"
    # incident timeline
    assert isinstance(d.get("incidents"), list) and any(
        i["id"] == inc_id and i["review_status"] == "PENDING" for i in d["incidents"]
    )
    # recent AI events
    assert isinstance(d.get("events"), list) and any(
        e["event_type"] == "OBJECT_PHONE" for e in d["events"]
    )
    # evidence viewer payload
    assert any(e["media_url"] and "image" in e["evidence_type"].lower() for e in d["evidence"])


def test_detail_unknown_session_404(client, teacher_headers):
    hh, _ = teacher_headers
    r = client.get("/api/proctoring/monitor/sessions/999999", headers=hh)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# live monitoring: Stage-3 pure signal persisted to SQL and reflected
# ---------------------------------------------------------------------------


def test_live_ingest_persists_to_sql_and_refreshes(client, teacher_headers):
    hh, (_, sess_id, _) = teacher_headers

    def _count(cls):
        db = SessionLocal()
        try:
            return db.query(cls).filter_by(exam_session_id=sess_id).count()
        finally:
            db.close()

    before_risk = _count(RiskScore)
    r = client.post(
        "/api/proctoring/monitor/ingest",
        headers=hh,
        json={
            "session_token": f"S4-TOKEN-{COUNTER['n']}",
            "observation": {
                "objects": [{"class_name": "phone", "confidence": 0.78}],
                "face": {"available": True, "face_count": 1, "faces": []},
                "head_pose": {},
                "audio": {"available": True, "speech_detected": False},
                "camera_available": True,
            },
        },
    )
    assert r.status_code == 200, r.text
    sig = r.json()
    # engine signal contract surfaces (risk never a verdict, candidates stay PENDING)
    assert "risk" in sig
    assert sig["risk"]["level"] in ("NORMAL", "ATTENTION", "ELEVATED", "HIGH")
    assert "incident_candidates" in sig
    # a risk snapshot is persisted on every ingest call -> detail is live from SQL
    assert _count(RiskScore) == before_risk + 1
    detail = client.get(f"/api/proctoring/monitor/sessions/{sess_id}", headers=hh).json()
    assert len(detail["risk_rows"]) == before_risk + 1


def test_live_overview_reflects_new_sql_rows(client, teacher_headers):
    """SQL is authoritative: a freshly persisted event+risk updates the grid
    without any in-memory monitoring state (the frontend polls this surface)."""
    hh, (_, sess_id, inc_id) = teacher_headers

    def _overview_row():
        body = client.get("/api/proctoring/monitor/overview", headers=hh).json()
        return next(x for x in body["sessions"] if x["id"] == sess_id)

    before = _overview_row()
    db = SessionLocal()
    try:
        db.add(
            AIServiceEvent(
                exam_session_id=sess_id,
                source="audio",
                event_type="SPEECH",
                severity="WATCH",
                confidence=0.55,
                repeat_count=1,
            )
        )
        db.add(
            RiskScore(
                exam_session_id=sess_id,
                level="HIGH",
                index_value=0.85,
                score=0.85,
                reason="Added speech after review.",
            )
        )
        db.commit()
    finally:
        db.close()
    after = _overview_row()
    assert after["event_count_24h"] == before["event_count_24h"] + 1
    assert after["risk_level"] == "HIGH"


def test_live_ingest_unknown_session_404(client, teacher_headers):
    hh, _ = teacher_headers
    r = client.post(
        "/api/proctoring/monitor/ingest",
        headers=hh,
        json={"session_token": "NOPE-999999", "observation": {"objects": []}},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# teacher review: the ONLY verdict maker — SQL-persisted + audited
# ---------------------------------------------------------------------------


def test_review_confirm_persisted_and_audited(client, teacher_headers):
    hh, (t_id, sess_id, inc_id) = teacher_headers
    r = client.post(
        "/api/proctoring/monitor/review",
        headers=hh,
        json={"incident_id": inc_id, "action": "CONFIRM", "remarks": "Phone clearly visible - flagging."},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["review_status"] == "CONFIRMED"
    assert out["ok"] is True

    # SQL is authoritative
    db = SessionLocal()
    try:
        inc = db.query(Incident).filter(Incident.id == inc_id).first()
        assert inc.review_status == "CONFIRMED"
        assert inc.reviewed_by == t_id
        assert inc.reviewed_at is not None
        assert inc.review_notes == "Phone clearly visible - flagging."
        assert inc.resolved is False  # CONFIRM keeps the incident open
        # audit trail
        assert db.query(AuditLog).filter(AuditLog.action == "PROCTORING:REVIEW:CONFIRM",
                                         AuditLog.entity_id == inc_id).count() == 1
    finally:
        db.close()

    # detail reflects the verdict
    after = client.get(f"/api/proctoring/monitor/sessions/{sess_id}", headers=hh).json()
    assert any(i["review_status"] == "CONFIRMED" for i in after["incidents"])
    overview = client.get("/api/proctoring/monitor/overview", headers=hh).json()
    row = next(x for x in overview["sessions"] if x["id"] == sess_id)
    assert row["pending_incidents"] == 0


def test_review_dismiss_and_resolve(client, teacher_headers):
    hh, (_, sess_id, inc_id) = teacher_headers

    r = client.post(
        "/api/proctoring/monitor/review",
        headers=hh,
        json={"incident_id": inc_id, "action": "DISMISS", "remarks": "Student turning to look at window."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "DISMISSED"
    assert r.json()["resolved"] is True

    db = SessionLocal()
    try:
        inc = db.query(Incident).filter(Incident.id == inc_id).first()
        assert inc.review_status == "DISMISSED"
        assert inc.resolved is True
        assert inc.review_notes == "Student turning to look at window."
    finally:
        db.close()

    inc2 = _new_incident()
    r = client.post(
        "/api/proctoring/monitor/review",
        headers=hh,
        json={"incident_id": inc2, "action": "RESOLVE", "remarks": "Resolved after teacher intervention."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "RESOLVED"
    assert r.json()["resolved"] is True


def test_review_unknown_incident_404_and_bad_action(client, teacher_headers):
    hh, _ = teacher_headers
    r = client.post("/api/proctoring/monitor/review", headers=hh,
                    json={"incident_id": 999999, "action": "CONFIRM"})
    assert r.status_code == 404
    db = SessionLocal()
    try:
        any_inc = db.query(Incident).first()
    finally:
        db.close()
    r = client.post("/api/proctoring/monitor/review", headers=hh,
                    json={"incident_id": any_inc.id, "action": "MAYBE"})
    assert r.status_code == 422


def _new_incident():
    db = SessionLocal()
    try:
        sess = db.query(ExamSession).first()
        inc = Incident(
            exam_session_id=sess.id,
            incident_type="GAZE",
            risk_level="ATTENTION",
            confidence=0.6,
            description="Repeated gaze deviation.",
            event_count=2,
            resolved=False,
            review_status="PENDING",
        )
        db.add(inc)
        db.commit()
        return inc.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# access control: teacher-only monitor surface
# ---------------------------------------------------------------------------


def test_monitor_requires_teacher(client, teacher_headers):
    # anonymous
    r = client.get("/api/proctoring/monitor/overview")
    assert r.status_code in (401, 403)
    # student role is forbidden
    iid = _next()
    db = SessionLocal()
    try:
        stu_user = User(
            email=f"st.review.{iid}@test.dev",
            password_hash=hash_password("Passw0rd!"),
            full_name="Stage-4 Student User",
            role="student",
            is_active=True,
        )
        db.add(stu_user)
        db.commit()
        uid = stu_user.id
    finally:
        db.close()
    r = client.post("/api/auth/login",
                    json={"email": f"st.review.{iid}@test.dev", "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    r = client.get("/api/proctoring/monitor/overview",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403