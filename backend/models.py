from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Float,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy import Enum as SqlEnum

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(SqlEnum("student", "teacher", "admin", name="user_role"), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_profile = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")
    exams_created = relationship("Exam", back_populates="creator")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("student_id", name="uq_students_student_id"),
        UniqueConstraint("email", name="uq_students_email"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)

    user = relationship("User", back_populates="student_profile")
    klass = relationship("ClassGroup", back_populates="students")
    enrollments = relationship("Enrollment", back_populates="student")
    assignments = relationship("ExamAssignment", back_populates="student")
    sessions = relationship("ExamSession", back_populates="student")

    created_at = Column(DateTime, default=datetime.utcnow)


class Teacher(Base):
    __tablename__ = "teachers"
    __table_args__ = (
        UniqueConstraint("teacher_id", name="uq_teachers_teacher_id"),
        UniqueConstraint("email", name="uq_teachers_email"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)

    user = relationship("User", back_populates="teacher_profile")
    exams = relationship("Exam", back_populates="teacher")

    created_at = Column(DateTime, default=datetime.utcnow)


class ClassGroup(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    students = relationship("Student", back_populates="klass")
    batch_assignments = relationship("ExamBatchAssignment", back_populates="klass")
    enrollments = relationship("Enrollment", back_populates="klass")

    created_at = Column(DateTime, default=datetime.utcnow)


class Enrollment(Base):
    """Records how a student was enrolled (individual or bulk import)."""
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True)
    student_id_db = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(20), nullable=False, default="manual")  # manual | bulk
    bulk_import_id = Column(Integer, ForeignKey("bulk_imports.id", ondelete="SET NULL"), nullable=True)
    imported_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="enrollments")
    klass = relationship("ClassGroup", back_populates="enrollments")


class BulkImport(Base):
    """A single Excel/CSV bulk enrollment run with its validation/import summary."""
    __tablename__ = "bulk_imports"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    total_rows = Column(Integer, nullable=False, default=0)
    valid_rows = Column(Integer, nullable=False, default=0)
    invalid_rows = Column(Integer, nullable=False, default=0)
    duplicate_rows = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="IMPORTED")  # PREVIEWED | IMPORTED | FAILED
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    rows = relationship("BulkImportRow", back_populates="bulk_import")


class BulkImportRow(Base):
    __tablename__ = "bulk_import_rows"

    id = Column(Integer, primary_key=True)
    bulk_import_id = Column(Integer, ForeignKey("bulk_imports.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer, nullable=False)
    student_id = Column(String(50), nullable=False)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    class_code = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")  # VALID | DUPLICATE | INVALID | IMPORTED | SKIPPED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bulk_import = relationship("BulkImport", back_populates="rows")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    exam_code = Column(String(50), unique=True, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    subject = Column(String(255), nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=60)
    total_marks = Column(Integer, nullable=False, default=0)
    status = Column(SqlEnum("DRAFT", "SCHEDULED", "AVAILABLE", "ACTIVE", "COMPLETED", "ARCHIVED", name="exam_status"), nullable=False, default="DRAFT", index=True)
    pass_marks = Column(Integer, nullable=True)
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    is_published = Column(Boolean, default=False, nullable=False)
    is_saved_draft = Column(Boolean, default=True, nullable=False)

    creator = relationship("User", back_populates="exams_created")
    teacher = relationship("Teacher", back_populates="exams")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan", order_by="Question.order_index")
    assignments = relationship("ExamAssignment", back_populates="exam", cascade="all, delete-orphan")
    batch_assignments = relationship("ExamBatchAssignment", back_populates="exam", cascade="all, delete-orphan")
    sessions = relationship("ExamSession", back_populates="exam")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    question_text = Column(Text, nullable=False)
    question_type = Column(SqlEnum("MCQ", name="question_type"), nullable=False, default="MCQ")
    marks = Column(Integer, nullable=False, default=1)
    option_a = Column(String(255), nullable=True)
    option_b = Column(String(255), nullable=True)
    option_c = Column(String(255), nullable=True)
    option_d = Column(String(255), nullable=True)
    correct_option = Column(String(1), nullable=True)  # A/B/C/D
    negative_marks = Column(Float, nullable=True, default=0)

    exam = relationship("Exam", back_populates="questions")
    answers = relationship("Answer", back_populates="question")
    created_at = Column(DateTime, default=datetime.utcnow)


class ExamAssignment(Base):
    """A student assigned (individually) to an exam."""
    __tablename__ = "exam_assignments"
    __table_args__ = (UniqueConstraint("exam_id", "student_id_db", name="uq_exam_student"),)

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    student_id_db = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    notify_at = Column(DateTime, nullable=True)

    exam = relationship("Exam", back_populates="assignments")
    student = relationship("Student", back_populates="assignments")


class ExamBatchAssignment(Base):
    """Entire batch/class assigned to an exam."""
    __tablename__ = "exam_batch_assignments"
    __table_args__ = (UniqueConstraint("exam_id", "class_id", name="uq_exam_class"),)

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    exam = relationship("Exam", back_populates="batch_assignments")
    klass = relationship("ClassGroup", back_populates="batch_assignments")


# --------------------------------------------------------------------------
# Stage 2+ extension tables: reserved now so later stages attach cleanly.
# --------------------------------------------------------------------------

class ExamSession(Base):
    """Stage 2: per-student live exam-taking session with autosave + timer.

    Lifecycle:
      PREPARING  -> created by the readiness wizard (identity/camera/mic/env checks)
      ACTIVE     -> student started the exam; timer running
      SUBMITTED  -> student submitted answers (or auto-submitted on expiry)
      EXPIRED    -> time ran out without an explicit submit
      ABANDONED  -> teacher/admin terminated (reserved)
    Instances are keyed by (exam_id, student_id_db) — resumed via session_token.
    """
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    student_id_db = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="PREPARING", index=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)          # = start_time + duration
    last_activity_at = Column(DateTime, nullable=True)  # heartbeat / autosave
    submitted_at = Column(DateTime, nullable=True)
    expired_at = Column(DateTime, nullable=True)

    exam = relationship("Exam", back_populates="sessions")
    student = relationship("Student", back_populates="sessions")
    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")
    readiness = relationship("ExamReadinessCheck", back_populates="session", uselist=False, cascade="all, delete-orphan")

    created_at = Column(DateTime, default=datetime.utcnow)


class ExamReadinessCheck(Base):
    """Stage 2: outcome of the pre-exam readiness wizard for a session.

    Recorded once per session before the timer starts: the student confirms
    their identity, and the browser camera / microphone / environment checks
    must have passed before the exam can be started.
    """
    __tablename__ = "exam_readiness_checks"

    id = Column(Integer, primary_key=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    identity_verified = Column(Boolean, default=False, nullable=False)
    identity_photo_path = Column(String(500), nullable=True)
    identity_confirmed_at = Column(DateTime, nullable=True)
    camera_checked = Column(Boolean, default=False, nullable=False)
    camera_checked_at = Column(DateTime, nullable=True)
    camera_error = Column(String(300), nullable=True)
    microphone_checked = Column(Boolean, default=False, nullable=False)
    microphone_checked_at = Column(DateTime, nullable=True)
    microphone_error = Column(String(300), nullable=True)
    environment_ready = Column(Boolean, default=False, nullable=False)
    environment_checked_at = Column(DateTime, nullable=True)
    env_notes = Column(String(500), nullable=True)

    session = relationship("ExamSession", back_populates="readiness")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Answer(Base):
    """Stage 2: submitted answer for a question, autosaved per session."""
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("exam_session_id", "question_id", name="uq_answer_session_question"),
    )

    id = Column(Integer, primary_key=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    selected_option = Column(String(1), nullable=True)
    marked_for_review = Column(Boolean, default=False, nullable=False)
    is_correct = Column(Boolean, nullable=True)
    marks_awarded = Column(Float, nullable=True)
    saved_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)

    session = relationship("ExamSession", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class AIServiceEvent(Base):
    """Reserved for Stage 3: AI monitoring events (YOLO/MediaPipe/PnP/Audio)."""
    __tablename__ = "ai_events"

    id = Column(Integer, primary_key=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(30), nullable=False)  # YOLO | MEDIAPIPE | PNP | AUDIO
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=True)
    payload = Column(Text, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Incident(Base):
    """Reserved for Stage 3: aggregated incident derived from AI events."""
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    incident_type = Column(String(50), nullable=False)
    risk_level = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    resolved = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RiskScore(Base):
    """Reserved for Stage 3: temporal risk evaluation per session."""
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    score = Column(Float, nullable=False, default=100)
    reason = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)


class Evidence(Base):
    """Reserved for Stage 3: captured evidence frames/clips."""
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    file_path = Column(String(500), nullable=False)
    media_type = Column(String(20), nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class Result(Base):
    """Reserved for Stage 5: final result records."""
    __tablename__ = "results"

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    student_id_db = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    score = Column(Float, nullable=True)
    total_marks = Column(Integer, nullable=True)
    percent = Column(Float, nullable=True)
    result_status = Column(String(20), nullable=True)
    published = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Audit history: tracks who did what, when."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_role = Column(String(20), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)