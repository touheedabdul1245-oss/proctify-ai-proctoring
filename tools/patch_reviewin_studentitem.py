"""Append the two census-confirmed wire surfaces the Stage-4 monitor router
imports but that the AST-census refused to emit (they are only imported and
constructed indirectly, so generation can't see a Name-call site).

Census ground truth (single source of truth = the router, verbatim from an
AST census of backend/routes/proctoring_monitor_routes.py):

  * ProctoringReviewIn   -> POST /review body; attrs census (payload.X):
                            incident_id, action, remarks
  * ProctoringStudentItemOut -> READ contract for a teacher-facing student
                            row; built via **item spread in the /students
                            census (evidence-count + risk + status surface).

Both are append-only so existing 7 classes stay byte-identical. extra=allow
keeps the contract permanently drift-proof against the router census.
"""
from pathlib import Path

SCHEMAS = Path(r"backend\schemas_stage4.py")
src = SCHEMAS.read_text(encoding="utf-8")

BLOCK = '''
class ProctoringReviewIn(BaseModel):
    model_config = _perm_allow()

    incident_id: int = 0
    action: str = "CONFIRM"
    remarks: str = ""


class ProctoringStudentItemOut(BaseModel):
    model_config = _perm_allow()

    student_id: int = 0
    student_name: str = ""
    student_email: str = ""
    exam_session_id: int = 0
    session_token: str = ""
    exam_id: int = 0
    exam_code: str = ""
    exam_title: str = ""
    session_status: str = ""
    risk_level: str = "NORMAL"
    risk_index: float = 0.0
    risk_factors: Optional[Dict[str, Any]] = None
    pending_incidents: int = 0
    incident_count: int = 0
    evidence_count: int = 0
    event_count_24h: int = 0
    camera_available: bool = False
    audio_available: bool = False
    monitor_status: str = "IDLE"
    last_activity_at: Optional[datetime] = None
'''

if "class ProctoringReviewIn" in src:
    print("ALREADY-PRESENT (nothing to do)")
else:
    src = src.rstrip() + "\n" + BLOCK
    SCHEMAS.write_text(src, encoding="utf-8")
    print("APPENDED ProctoringReviewIn + ProctoringStudentItemOut")
