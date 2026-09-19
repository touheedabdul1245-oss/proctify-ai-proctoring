"""Stage-4 teacher-side monitor wire contracts.

Deterministic contract map derived directly from the census of
``backend/routes/proctoring_monitor_routes.py`` (the ONLY thing that imports
this module) — every class/field name below is exactly the one the router
constructs; nothing here invents new surfacescars.  SQL stays authoritative
(Stage-1/2/3 tables) and the engine never verdicts (Stage-3 guarantee);
teacher review (ProctoringReviewIn) is the single human verdict persisted
to SQL + audited.

All models are permissive ``extra="allow"`` so the read surface can never
drift from what the router emits — the contract is the census, and the
census is the file below.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict

_P = ConfigDict(extra="allow")


class ProctoringMonitorSessionRow(BaseModel):
    model_config = _P

    id: int = 0
    exam_session_id: int = 0
    exam_id: int = 0
    exam_code: str = ""
    exam_title: str = ""
    session_token: str = ""
    status: str = ""
    student_id: int = 0
    student_name: str = ""
    student_email: str = ""
    risk_level: str = "NORMAL"
    risk_index: float = 0.0
    risk_factors: Optional[Dict[str, Any]] = None
    pending_incidents: int = 0
    incident_count: int = 0
    evidence_count: int = 0
    event_count_24h: int = 0
    recent_events: List[Dict[str, Any]] = []
    camera_available: bool = False
    audio_available: bool = False
    monitor_status: str = "IDLE"
    last_activity_at: Optional[datetime] = None
    trust_score: float = 100.0
    trust_level: str = "NORMAL"
    trust_delta: float = 0.0


class ProctoringMonitorTrustRow(BaseModel):
    model_config = _P

    id: int = 0
    trust_score: float = 100.0
    delta: float = 0.0
    level: str = "NORMAL"
    source: str = ""
    reason: str = ""
    event_types: Optional[List[str]] = None
    recorded_at: Optional[datetime] = None


class ProctoringMonitorRiskRow(BaseModel):
    model_config = _P

    id: int = 0
    level: str = "NORMAL"
    risk_index: float = 0.0
    index_value: Optional[float] = None
    score: Optional[float] = None
    reason: str = ""
    factors: Optional[Union[Dict[str, Any], List[Any]]] = None
    recorded_at: Optional[datetime] = None


class ProctoringMonitorEvidenceCard(BaseModel):
    model_config = _P

    id: int = 0
    evidence_id: int = 0
    incident_id: Optional[int] = None
    source: str = ""
    evidence_type: str = "IMAGE"
    media_url: str = ""
    description: str = ""
    captured_at: Optional[datetime] = None


class ProctoringMonitorIncidentCard(BaseModel):
    model_config = _P

    id: int = 0
    incident_id: int = 0
    incident_type: str = ""
    risk_level: str = "NORMAL"
    confidence: Optional[float] = None
    description: str = ""
    event_count: int = 0
    event_types: Optional[List[str]] = None
    first_event_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    review_status: str = "PENDING"
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_notes: str = ""
    resolved: bool = False
    evidence: List[ProctoringMonitorEvidenceCard] = []


class ProctoringMonitorSummary(BaseModel):
    model_config = _P

    sessions: List[ProctoringMonitorSessionRow] = []
    total_sessions: int = 0
    live_count: int = 0
    attention_count: int = 0
    elevated_count: int = 0
    high_count: int = 0
    pending_total: int = 0
    contract: Optional[Dict[str, Any]] = None


class ProctoringMonitorDetail(BaseModel):
    model_config = _P

    id: int = 0
    exam_session_id: int = 0
    exam_id: int = 0
    exam_code: str = ""
    exam_title: str = ""
    session_token: str = ""
    status: str = ""
    student_id: int = 0
    student_name: str = ""
    student_email: str = ""
    risk_level: str = "NORMAL"
    risk_index: float = 0.0
    risk_factors: Optional[Dict[str, Any]] = None
    risk_rows: List[ProctoringMonitorRiskRow] = []
    trust_score: float = 100.0
    trust_level: str = "NORMAL"
    trust_rows: List[ProctoringMonitorTrustRow] = []
    incidents: List[ProctoringMonitorIncidentCard] = []
    evidence: List[ProctoringMonitorEvidenceCard] = []
    events: List[Dict[str, Any]] = []
    pending_incidents: int = 0
    camera_available: bool = False
    audio_available: bool = False
    monitor_status: str = "IDLE"
    last_activity_at: Optional[datetime] = None
    camera_frame: Optional[str] = None
    alert_tone: Optional[str] = None


class ProctoringReviewIn(BaseModel):
    model_config = _P

    incident_id: int
    action: str = "CONFIRM"
    remarks: str = ""


class ProctoringReviewOut(BaseModel):
    model_config = _P

    incident_id: int
    action: str = "CONFIRM"
    review_status: str = "PENDING"
    resolved: bool = False
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    remarks: str = ""
    ok: bool = True
    message: str = ""


class ProctoringStudentItemOut(BaseModel):
    model_config = _P

    id: int = 0
    exam_session_id: int = 0
    student_id: int = 0
    student_name: str = ""
    student_email: str = ""
    exam_id: int = 0
    exam_code: str = ""
    exam_title: str = ""
    session_token: str = ""
    status: str = ""
    risk_level: str = "NORMAL"
    risk_index: float = 0.0
    trust_score: float = 100.0
    trust_level: str = "NORMAL"
    monitor_status: str = "IDLE"
    last_activity_at: Optional[datetime] = None
