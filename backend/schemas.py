from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .usernames import USERNAME_RE


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    role: str = Field(pattern="^(student|teacher|admin)$")
    username: Optional[str] = Field(default=None, pattern=USERNAME_RE)

    # extra for student/teacher profiles
    student_id: Optional[str] = None
    class_code: Optional[str] = None
    teacher_id: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, pattern=USERNAME_RE)
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6)
    class_code: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: Optional[str] = None
    full_name: str
    role: str
    is_active: bool


class UserDetail(UserOut):
    student_id: Optional[str] = None
    teacher_id: Optional[str] = None
    class_id: Optional[int] = None
    class_code: Optional[str] = None
    class_name: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

class StudentCreate(BaseModel):
    student_id: str
    username: Optional[str] = Field(default=None, pattern=USERNAME_RE)
    email: EmailStr
    full_name: str
    password: Optional[str] = Field(default=None, min_length=6)
    class_code: Optional[str] = None


class StudentUpdate(BaseModel):
    student_id: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    class_code: Optional[str] = None
    is_active: Optional[bool] = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    student_id: str
    email: str
    username: Optional[str] = None
    full_name: str
    class_id: Optional[int] = None
    class_code: Optional[str] = None
    class_name: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Bulk enrollment
# ---------------------------------------------------------------------------

class BulkImportRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    row_number: int
    student_id: str
    full_name: str
    email: str
    class_code: Optional[str] = None
    status: str
    error_message: Optional[str] = None


class BulkPreviewOut(BaseModel):
    preview_id: int
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    new_rows: int
    invalid: List[BulkImportRowOut] = []
    duplicates: List[BulkImportRowOut] = []
    new: List[BulkImportRowOut] = []


class BulkImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    imported_count: int
    summary: Optional[str]
    status: str
    created_at: datetime


class BulkImportSummary(BaseModel):
    import_id: int
    imported: int
    skipped_duplicates: int
    invalid: int
    errors: List[str] = []


# ---------------------------------------------------------------------------
# Classes / Batches
# ---------------------------------------------------------------------------

class ClassCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class ClassUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    student_count: Optional[int] = 0
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------

class OptionPayload(BaseModel):
    option: str  # A/B/C/D
    text: str


class QuestionCreate(BaseModel):
    question_text: str
    order_index: Optional[int] = 0
    marks: int = 1
    options: List[OptionPayload] = Field(min_length=2, max_length=4)
    correct_option: str = Field(pattern="^[ABCD]$")
    negative_marks: Optional[float] = 0


class QuestionUpdate(QuestionCreate):
    pass


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exam_id: int
    order_index: int
    question_text: str
    question_type: str
    marks: int
    option_a: Optional[str]
    option_b: Optional[str]
    option_c: Optional[str]
    option_d: Optional[str]
    correct_option: Optional[str]
    negative_marks: Optional[float]


class ExamCreate(BaseModel):
    title: str
    description: Optional[str] = None
    subject: Optional[str] = None
    duration_minutes: int = 60
    total_marks: Optional[int] = 0
    pass_marks: Optional[int] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    save_as_draft: Optional[bool] = True


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    subject: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_marks: Optional[int] = None
    pass_marks: Optional[int] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None


class ExamAssignPayload(BaseModel):
    student_ids: List[int] = Field(default_factory=list)
    class_ids: List[int] = Field(default_factory=list)


class ExamSchedulePayload(BaseModel):
    scheduled_start: datetime
    scheduled_end: datetime


class ExamStatusChange(BaseModel):
    target_status: str = Field(pattern="^(DRAFT|SCHEDULED|AVAILABLE|ACTIVE|COMPLETED|CANCELLED|TERMINATED|ARCHIVED)$")


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str]
    exam_code: str
    subject: Optional[str]
    duration_minutes: int
    total_marks: int
    status: str
    pass_marks: Optional[int]
    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    is_published: bool
    is_saved_draft: bool
    question_count: Optional[int] = 0
    assigned_student_count: Optional[int] = 0
    created_by: Optional[int]
    created_at: Optional[datetime]


class ExamDetail(ExamOut):
    questions: List[QuestionOut] = []
    assigned_students: List[StudentOut] = []
    assigned_batches: List[ClassOut] = []
    assignment_summary: Optional[dict] = None


# ---------------------------------------------------------------------------
# Student-facing
# ---------------------------------------------------------------------------

class AssignedExamOut(BaseModel):
    exam_id: int
    title: str
    description: Optional[str]
    subject: Optional[str]
    exam_code: str
    duration_minutes: int
    total_marks: int
    status: str
    is_published: bool
    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    question_count: int
    assigned_via: List[str] = []


class ProfileOut(BaseModel):
    user: UserOut
    student_id: Optional[str] = None
    teacher_id: Optional[str] = None
    class_code: Optional[str] = None
    class_name: Optional[str] = None
    enrolled_total: Optional[int] = None
    assigned_exam_count: Optional[int] = None


# ---------------------------------------------------------------------------
# AI Service health
# ---------------------------------------------------------------------------

class AIHealthOut(BaseModel):
    yolo: dict
    mediapipe: dict
    pnp: dict
    audio: dict


# ---------------------------------------------------------------------------
# Stage 2 — exam sessions (readiness, MCQ taking, submission)
# ---------------------------------------------------------------------------

class ReadinessOut(BaseModel):
    identity_verified: bool = False
    identity_photo_path: Optional[str] = None
    camera_checked: bool = False
    camera_error: Optional[str] = None
    microphone_checked: bool = False
    microphone_error: Optional[str] = None
    environment_ready: bool = False
    env_notes: Optional[str] = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_token: str
    exam_id: int
    status: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    last_activity_at: Optional[datetime]
    submitted_at: Optional[datetime]
    expired_at: Optional[datetime]
    readiness: Optional[ReadinessOut] = None
    remaining_seconds: Optional[int] = None


class SessionStateOut(BaseModel):
    """Aggregate used by the 'My Exams' page to decide Start / Resume / Done."""
    session_token: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    remaining_seconds: Optional[int] = None


class SessionCreateOut(BaseModel):
    session_token: str
    status: str
    exam_id: int


class ReadinessSubmit(BaseModel):
    identity_verified: Optional[bool] = None
    identity_photo_data: Optional[str] = None  # base64 data-URL still image
    camera_checked: Optional[bool] = None
    camera_error: Optional[str] = None
    microphone_checked: Optional[bool] = None
    microphone_error: Optional[str] = None
    environment_ready: Optional[bool] = None
    env_notes: Optional[str] = None


class PaperQuestionOut(BaseModel):
    id: int
    order_index: int
    question_text: str
    marks: int
    negative_marks: Optional[float]
    option_a: Optional[str]
    option_b: Optional[str]
    option_c: Optional[str]
    option_d: Optional[str]


class PaperAnswerOut(BaseModel):
    question_id: int
    selected_option: Optional[str] = None
    marked_for_review: bool = False
    saved_at: Optional[datetime] = None


class PaperOut(BaseModel):
    session_token: str
    status: str
    exam_id: int
    title: str
    description: Optional[str] = None
    duration_minutes: int
    total_marks: int
    question_count: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    remaining_seconds: Optional[int] = None
    questions: List[PaperQuestionOut] = []
    answers: List[PaperAnswerOut] = []


class AnswerSavePayload(BaseModel):
    selected_option: Optional[str] = Field(default=None, pattern="^(A|B|C|D)?$")
    marked_for_review: Optional[bool] = None


class AnswerSaveOut(BaseModel):
    question_id: int
    selected_option: Optional[str] = None
    marked_for_review: bool = False
    saved_at: datetime


class SubmitResponse(BaseModel):
    session_token: str
    status: str
    total_questions: int
    answered_count: int
    marked_count: int
    unanswered_count: int
    submitted_at: Optional[datetime] = None
    auto: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# Stage 3 — proctoring ingest + risk/incident surfaces
# ---------------------------------------------------------------------------

class ProctoringIngestIn(BaseModel):
    """One client payload for the proctoring ingest endpoint.

    ``session_token`` is the exam-session token the student is running under.
    Exactly one of ``observation`` / ``frame_data_url`` should be present:
      * ``observation`` — a decoded observation dict (object detections, face,
        head pose, audio flags) produced by the client/AI layer;
      * ``frame_data_url`` — a base64 data-URL image; decoded server-side into
        a camera observation. ``camera_available`` may accompany it.
    ``camera_available`` / ``audio_available`` flags are used when only a raw
    frame is supplied so availability gating stays honest.
    """

    session_token: str = Field(min_length=8)
    observation: Optional[Dict[str, Any]] = None
    frame_data_url: Optional[str] = None
    camera_available: bool = True
    audio_available: bool = True


class TrustOut(BaseModel):
    """Stage-6 numeric trust snapshot (0..100) returned with each signal.

    ``score`` is the current live 0..100 value, ``level`` its band
    (NORMAL/ATTENTION/ELEVATED/HIGH per TRUST_SCORE_RANGES), ``delta`` the
    change since the previous ingest (negative = penalty, positive =
    recovery), and ``source``/``reason`` explain where it came from.
    """

    score: float = 100.0
    level: str = "NORMAL"
    delta: float = 0.0
    source: str = "baseline"
    reason: str = ""


class ProctoringSignalOut(BaseModel):
    """Compact, deterministic signal dict returned per ingest (the engine's
    snapshot contract). Incidents are ALWAYS PENDING for human review; risk
    only ever labels suspicion — never a verdict."""

    risk: Dict[str, Any]
    runs: Optional[Dict[str, int]] = None
    repeated: Optional[Dict[str, int]] = None
    incident_candidates: Optional[List[Dict[str, Any]]] = None
    trust: TrustOut = TrustOut()


# ---------------------------------------------------------------------------
# Teacher live-student list (SQL-authoritative, powers the dashboard table)
# ---------------------------------------------------------------------------

class LiveStudentRow(BaseModel):
    """One assigned (student, exam) row for the teacher dashboard's live list.

    ``status`` is the session status the student is in for that exam
    (NOT_STARTED / PREPARING / IN_PROGRESS / SUBMITTED / EXPIRED / TERMINATED),
    NOT a verdict. ``monitor_status`` is LIVE only while a session is actively
    streaming AI signals for a still-ACTIVE exam/session. Trust, risk, camera,
    mic and incidents are read from SQL only — never computed in the browser.
    """

    exam_id: int
    exam_code: str
    exam_title: str
    exam_status: str
    student_db_id: int
    student_id: str
    student_name: str
    student_email: str
    status: str
    monitor_status: str
    session_id: Optional[int] = None
    session_token: Optional[str] = None
    session_started_at: Optional[datetime] = None
    session_ends_at: Optional[datetime] = None
    trust_score: Optional[float] = None
    trust_level: str = "NORMAL"
    risk_level: str = "NORMAL"
    risk_index: Optional[float] = None
    camera: bool = False
    microphone: bool = False
    pending_incidents: int = 0
    incident_count: int = 0
    evidence_count: int = 0
    event_count_24h: int = 0
    last_activity_at: Optional[datetime] = None
    latest_event: Optional[str] = None


class LiveStudentsOut(BaseModel):
    exams: int = 0
    students: int = 0
    live_count: int = 0
    in_progress_count: int = 0
    preparing_count: int = 0
    not_started_count: int = 0
    submitted_count: int = 0
    expired_count: int = 0
    terminated_count: int = 0
    elevated_risk: int = 0
    pending_incidents: int = 0
    rows: List[LiveStudentRow] = []


class ProctoringBandsOut(BaseModel):
    bands: Dict[str, Any]
    simulate_allowed: bool = False
