"""Stage 5 — analytics dashboards.

Read-only aggregation over the same SQL tables the rest of the app trusts.
Role-aware overview endpoints keep the numbers meaningful per actor; exam
analytics give teachers distribution + per-question difficulty + proctoring
summary per exam.
"""
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_teacher
from ..database import get_db
from ..models import (
    AIServiceEvent,
    AuditLog,
    Exam,
    ExamAssignment,
    ExamSession,
    Incident,
    Question,
    Result,
    RiskScore,
    Student,
    User,
)
from ..schemas_stage5 import AnalyticsOverviewOut, ExamAnalyticsOut

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

CLOSED = ("SUBMITTED", "EXPIRED")


def _latest_risk(sess: ExamSession) -> Optional[RiskScore]:
    if not sess.risk_rows:
        return None
    return max(sess.risk_rows, key=lambda x: x.recorded_at or x.id)


def _distribute(values: List[Optional[float]], start=0, step=10):
    if not values:
        return []
    vals = [v for v in values if v is not None]
    if not vals:
        return []
    hi = min(100, max(int(max(vals)) + step - 1, 0))
    out = []
    for lo in range(0, hi + 1, step):
        hi_b = lo + step
        n = sum(1 for v in vals if lo <= v < hi_b)
        if n or hi_b > hi:
            out.append({"from": lo, "to": hi_b, "count": n})
    return out


@router.get("/overview", response_model=AnalyticsOverviewOut)
def analytics_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "student":
        st = current_user.student_profile
        if not st:
            raise HTTPException(status_code=404, detail="Student profile not found")
        assigned = (
            db.query(ExamAssignment)
            .filter(ExamAssignment.student_id_db == st.id)
            .count()
        )
        results = (
            db.query(Result)
            .filter(Result.student_id_db == st.id)
            .all()
        )
        published = [r for r in results if r.published]
        avg_percent = None
        if published and any(r.percent is not None for r in published):
            percents = [r.percent for r in published if r.percent is not None]
            avg_percent = round(sum(percents) / len(percents), 2)
        closed_sessions = (
            db.query(ExamSession)
            .filter(
                ExamSession.student_id_db == st.id,
                ExamSession.status.in_(CLOSED),
            )
            .count()
        )
        audits = (
            db.query(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(5)
            .all()
        )
        return AnalyticsOverviewOut(
            role="student",
            totals={
                "assigned": assigned,
                "attempted": closed_sessions,
                "results": len(results),
                "published_results": len(published),
            },
            results={
                "avg_percent": avg_percent,
                "published_count": len(published),
                "best_percent": max((r.percent for r in published if r.percent is not None), default=None),
            },
            risk_distribution={},
            incident_summary={},
            recent_activity=[
                {"action": a.action, "created_at": a.created_at}
                for a in audits
            ],
        )

    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="No analytics access")

    exams_total = db.query(Exam).count()
    students_total = db.query(Student).count()
    sessions_total = db.query(ExamSession).count()
    results_total = db.query(Result).count()
    published_total = db.query(Result).filter(Result.published.is_(True)).count()
    incidents_pending = (
        db.query(Incident).filter(Incident.review_status == "PENDING").count()
    )
    incidents_confirmed = db.query(Incident).filter(Incident.review_status == "CONFIRMED").count()
    incidents_dismissed = (
        db.query(Incident)
        .filter(Incident.review_status.in_(["DISMISSED", "RESOLVED"]))
        .count()
    )

    risk_dist: Counter = Counter()
    for sess in db.query(ExamSession).filter(ExamSession.status.in_(CLOSED)).all():
        r = _latest_risk(sess)
        risk_dist[(r.level if r else "NORMAL").upper()] += 1

    audits = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
        .all()
    )
    actor_ids = {a.actor_id for a in audits if a.actor_id}
    emails = {}
    if actor_ids:
        for u in db.query(User.id, User.email).filter(User.id.in_(actor_ids)).all():
            emails[u[0]] = u[1]
    return AnalyticsOverviewOut(
        role=current_user.role,
        totals={
            "exams": exams_total,
            "students": students_total,
            "sessions": sessions_total,
            "results": results_total,
            "published_results": published_total,
            "pending_incidents": incidents_pending,
            "confirmed_incidents": incidents_confirmed,
            "resolved_incidents": incidents_dismissed,
        },
        results={
            "published_count": published_total,
            "unpublished_count": results_total - published_total,
        },
        risk_distribution=dict(risk_dist),
        incident_summary={
            "PENDING": incidents_pending,
            "CONFIRMED": incidents_confirmed,
            "DISMISSED": incidents_dismissed,
        },
        recent_activity=[
            {
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "actor_email": emails.get(a.actor_id),
                "created_at": a.created_at,
            }
            for a in audits
        ],
    )


@router.get("/exams/{exam_id}", response_model=ExamAnalyticsOut)
def exam_analytics(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    results = (
        db.query(Result)
        .filter(Result.exam_id == exam_id)
        .order_by(Result.id)
        .all()
    )
    percents = [r.percent for r in results if r.percent is not None]
    submitted = len(results)
    avg_p = round(sum(percents) / len(percents), 2) if percents else None
    mid = len(percents) // 2
    median_p = None
    if sorted(percents):
        med = sorted(percents)
        median_p = round(med[mid] if len(med) % 2 else (med[mid - 1] + med[mid]) / 2, 2)
    pass_count = sum(1 for r in results if r.result_status == "PASS")
    fail_count = sum(1 for r in results if r.result_status == "FAIL")
    pass_rate = round(pass_count / submitted * 100.0, 2) if submitted else None

    questions = (
        db.query(Question)
        .filter(Question.exam_id == exam_id)
        .order_by(Question.order_index)
        .all()
    )
    q_difficulty = []
    if submitted:
        for q in questions:
            attempted = 0
            correct = 0
            for sess in exam.sessions:
                for a in sess.answers:
                    if a.question_id == q.id:
                        attempted += 1
                        if a.is_correct:
                            correct += 1
            facility = round(correct / attempted * 100.0, 1) if attempted else None
            q_difficulty.append({
                "question_id": q.id,
                "order_index": q.order_index,
                "facility": facility,
                "attempted": attempted,
                "correct": correct,
            })

    incident_types: Counter = Counter()
    for sess in exam.sessions:
        for i in sess.incidents or []:
            incident_types[i.incident_type or "UNKNOWN"] += 1

    events = (
        db.query(AIServiceEvent.occurred_at)
        .join(ExamSession, AIServiceEvent.exam_session_id == ExamSession.id)
        .filter(ExamSession.exam_id == exam_id)
        .all()
    )
    trend: Counter = Counter()
    for (occ,) in events:
        if occ:
            trend[occ.date().isoformat()] += 1
    day = datetime.utcnow().date() - timedelta(days=9)
    event_trend = []
    for _ in range(10):
        k = day.isoformat()
        event_trend.append({"date": k, "count": trend.get(k, 0)})
        day += timedelta(days=1)

    return ExamAnalyticsOut(
        exam_id=exam.id,
        exam_title=exam.title,
        exam_code=exam.exam_code,
        submitted=submitted,
        avg_percent=avg_p,
        median_percent=median_p,
        low_score=min(percents) if percents else None,
        high_score=max(percents) if percents else None,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=pass_rate,
        score_distribution=_distribute(percents),
        question_difficulty=q_difficulty,
        incident_summary=dict(incident_types),
        event_trend=event_trend,
    )