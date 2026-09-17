from datetime import datetime, date
from typing import List, Optional, Union

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
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

    # extra for student/teacher profiles
    student_id: Optional[str] = None
    class_code: Optional[str] = None
    teacher_id: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6)
    class_code: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
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
    target_status: str = Field(pattern="^(DRAFT|SCHEDULED|AVAILABLE|ACTIVE|COMPLETED|ARCHIVED)$")


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