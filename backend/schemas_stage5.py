"""Stage-5 wire contracts: results, reports, analytics, notifications and the
student live-proctoring feed.

Same convention as Stage-4: permissive ``extra="allow"`` models authored from a
census of exactly what the Stage-5 routers construct, so the read surface can
never drift from the code that builds it. SQL stays authoritative; nothing in
Stage 5 auto-verdicts (incidents remain teacher-reviewed).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

_P = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Results / reports
# ---------------------------------------------------------------------------

class StudentResultOut(BaseModel):
    model_config = _P

    result_id: int = 0
    exam_id: int = 0
    exam_title: str = ""
    exam_code: str = ""
    score: float = 0.0
    total_marks: int = 0
    percent: Optional[float] = None
    result_status: str = "GRADED"
    published: bool = False
    session_token: str = ""
    session_status: str = ""
    submitted_at: Optional[datetime] = None
    published_at: Optional[datetime] = None


class GradedAnswerOut(BaseModel):
    model_config = _P

    question_id: int = 0
    order_index: int = 0
    question_text: str = ""
    marks: int = 1
    selected_option: Optional[str] = None
    correct_option: Optional[str] = None
    is_correct: Optional[bool] = None
    marks_awarded: float = 0.0


class StudentResultDetailOut(StudentResultOut):
    questions: List[GradedAnswerOut] = []


class MonitoringSummaryOut(BaseModel):
    model_config = _P

    risk_level: str = "NORMAL"
    risk_index: float = 0.0
    event_count: int = 0
    pending_incidents: int = 0
    confirmed_incidents: int = 0
    dismissed_incidents: int = 0
    evidence_count: int = 0


class TeacherResultRowOut(BaseModel):
    model_config = _P

    result_id: int = 0
    student_id: int = 0
    student_name: str = ""
    student_email: str = ""
    score: float = 0.0
    total_marks: int = 0
    percent: Optional[float] = None
    result_status: str = "GRADED"
    published: bool = False
    session_token: str = ""
    submitted_at: Optional[datetime] = None


class TeacherResultDetailOut(TeacherResultRowOut):
    exam_id: int = 0
    exam_title: str = ""
    exam_code: str = ""
    risk_level: str = "NORMAL"
    risk_index: float = 0.0
    incidents: List[Dict[str, Any]] = []
    event_count: int = 0
    evidence_count: int = 0


class ResultPublishOut(BaseModel):
    model_config = _P

    result_id: int = 0
    published: bool = False
    published_by: Optional[int] = None
    published_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Student live proctoring feed
# ---------------------------------------------------------------------------

class ProctoringFeedConfigOut(BaseModel):
    model_config = _P

    enabled: bool = False
    poll_interval_seconds: int = 5
    max_frame_bytes: int = 300 * 1024
    bands: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class AnalyticsOverviewOut(BaseModel):
    model_config = _P

    role: str = ""
    totals: Dict[str, int] = {}
    results: Dict[str, Any] = {}
    risk_distribution: Dict[str, int] = {}
    incident_summary: Dict[str, Any] = {}
    recent_activity: List[Dict[str, Any]] = []


class ExamAnalyticsOut(BaseModel):
    model_config = _P

    exam_id: int = 0
    exam_title: str = ""
    exam_code: str = ""
    submitted: int = 0
    avg_percent: Optional[float] = None
    median_percent: Optional[float] = None
    low_score: Optional[float] = None
    high_score: Optional[float] = None
    pass_count: int = 0
    fail_count: int = 0
    pass_rate: Optional[float] = None
    score_distribution: List[Dict[str, Any]] = []
    question_difficulty: List[Dict[str, Any]] = []
    incident_summary: Dict[str, Any] = {}
    event_trend: List[Dict[str, Any]] = []