"""Stage 5 — student live proctoring feed (browser -> server AI).

The student's camera posts small JPEG frames (~every ``poll_interval_seconds``)
during an ACTIVE session. The server decodes the frame, runs the EXISTING
Stage-1 AI services (YOLO / MediaPipe / PnP) through ``ai_service.pipeline``,
feeds the SHARED per-session engine registry, and persists events / risk /
incidents (PENDING, teacher-reviewed) / evidence via the same
``proctoring_service`` used by the teacher ingest surface.

Guards:
  * owner check — a student may only feed THEIR OWN active session;
  * session must be ACTIVE (config reports ``enabled=False`` otherwise);
  * per-session rate limit (min interval derived from the poll cadence);
  * frame size cap (config-visible) to bound uploads;
  * graceful degradation — a client that cannot capture camera/audio simply
    reports the flags; the pipeline folds them into the observation.
"""
import base64
import time
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai_service.pipeline import build_observation
from ..auth import get_current_user
from ..database import get_db
from ..models import ExamSession, Student, User
from ..schemas import ProctoringIngestIn, ProctoringSignalOut
from ..schemas_stage5 import ProctoringFeedConfigOut
from ..services.proctoring_service import ingest_and_persist

router = APIRouter(prefix="/api/student/sessions", tags=["student-proctoring"])

DEFAULT_POLL_SECONDS = 5
MAX_FRAME_BYTES = 300 * 1024

_last_ingest: Dict[int, float] = {}
_LOCK = __import__("threading").Lock()


def _student(db: Session, user: User) -> Student:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Students only")
    st = user.student_profile
    if not st:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return st


def _own_active_session(db: Session, st: Student, token: str) -> ExamSession:
    sess = (
        db.query(ExamSession)
        .filter(ExamSession.session_token == token, ExamSession.student_id_db == st.id)
        .first()
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


def _decode_frame(frame_data_url: str) -> Optional[bytes]:
    if not frame_data_url or "," not in frame_data_url:
        return None
    prefix, _, b64 = frame_data_url.partition(",")
    if not prefix.endswith(";base64") and "base64" not in prefix:
        return None
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        return None
    return raw or None


def _to_frame_array(raw: bytes):
    """Decode encoded image bytes to a numpy BGR frame for the vision pipeline."""
    try:
        import cv2
        import numpy as np

        arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        return arr if arr is not None else None
    except Exception:
        return None


@router.get("/{token}/proctoring/config", response_model=ProctoringFeedConfigOut)
def proctoring_config(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    st = _student(db, current_user)
    sess = _own_active_session(db, st, token)
    exam = sess.exam
    enabled = bool(
        exam
        and sess.status == "ACTIVE"
        and sess.start_time is not None
    )
    return ProctoringFeedConfigOut(
        enabled=enabled,
        poll_interval_seconds=DEFAULT_POLL_SECONDS,
        max_frame_bytes=MAX_FRAME_BYTES,
    )


@router.post("/{token}/proctoring", response_model=ProctoringSignalOut)
def proctoring_ingest_student(
    token: str,
    payload: ProctoringIngestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    st = _student(db, current_user)
    sess = _own_active_session(db, st, token)
    if sess.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"Session not active ({sess.status})")
    if sess.start_time is None:
        raise HTTPException(status_code=409, detail="Session has not started yet")
    if not sess.exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Per-session rate limit aligned with the documented poll cadence.
    with _LOCK:
        last = _last_ingest.get(sess.id, 0.0)
        now = time.monotonic()
        if now - last < DEFAULT_POLL_SECONDS * 0.75:
            retry = int(DEFAULT_POLL_SECONDS * 0.75 - (now - last)) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Proctoring frames are rate limited; retry in {retry}s",
            )
        _last_ingest[sess.id] = now

    observation = dict(payload.observation or {})
    frame_bytes = None
    if observation.get("camera_available") and observation.get("frame_data_url"):
        frame_bytes = _decode_frame(observation.pop("frame_data_url"))
        if frame_bytes is None:
            raise HTTPException(status_code=422, detail="Unreadable frame payload")
        if len(frame_bytes) > MAX_FRAME_BYTES:
            raise HTTPException(status_code=413, detail="Frame too large")

    if frame_bytes is not None:
        # server-side AI: server-decoded frame wins over any client numbers
        arr = _to_frame_array(frame_bytes)
        if arr is None:
            raise HTTPException(status_code=422, detail="Unreadable frame payload")
        obs = build_observation(arr, audio=observation.get("audio"))
        observation.update(obs)

    # No frame attached -> the observation is already normalized (the client
    # reported camera_available/objects/audio); a camera-less client says
    # camera_available=False + empty objects so the engine emits the honest
    # CAMERA_UNAVAILABLE signal instead of missing data silently.

    result = ingest_and_persist(
        db,
        current_user,
        sess,
        observation,
        frame_bytes=frame_bytes,
    )
    db.commit()
    return ProctoringSignalOut(
        risk=result.get("risk", {}),
        runs=result.get("runs"),
        repeated=result.get("repeated"),
        incident_candidates=result.get("incident_candidates"),
    )