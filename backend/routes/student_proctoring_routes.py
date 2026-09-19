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
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai_service.audio_interface import audio_service
from ..ai_service.pipeline import build_observation
from ..auth import get_current_user
from ..database import get_db
from ..models import ExamSession, Student, User
from ..schemas import ProctoringIngestIn, ProctoringSignalOut, TrustOut
from ..schemas_stage5 import ProctoringFeedConfigOut
from ..services.proctoring_service import ingest_and_persist

router = APIRouter(prefix="/api/student/sessions", tags=["student-proctoring"])

DEFAULT_POLL_SECONDS = 5
MAX_FRAME_BYTES = 300 * 1024
MAX_PCM_BYTES = 128 * 1024
DEFAULT_PCM_SAMPLE_RATE = 16000

_last_ingest: Dict[int, float] = {}
_MAX_TRACKED_SESSIONS = 1024
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


def _analyze_audio(observation: Dict[str, Any]) -> None:
    """Run REAL server-side speech analysis on a client PCM chunk.

    The client captures mic audio (downsampled 16 kHz Int16 mono), base64s it
    into ``audio.pcm_data`` (with ``audio.sample_rate``) and posts it with the
    observation. Here we decode the chunk and replace the audio context with
    actual results from the SAME ``audio_service`` the health report exposes —
    RMS, zero-crossing, voice-band ratio and a speech flag. ``available`` stays
    honest: no samples, an undecodable chunk or an oversized payload means
    audio is NOT available, and the engine emits AUDIO_UNAVAILABLE instead of
    silently reporting a speech signal."""

    audio = observation.get("audio")
    if not isinstance(audio, dict) or not audio.get("available"):
        observation["audio_unavailable"] = not bool(
            isinstance(audio, dict) and audio.get("available")
        )
        return
    pcm_b64 = audio.pop("pcm_data", None)
    if not pcm_b64:
        observation["audio"] = audio
        observation["audio_unavailable"] = False
        return
    try:
        raw = base64.b64decode(pcm_b64, validate=True)
        if not raw:
            raise ValueError("empty PCM chunk")
        if len(raw) > MAX_PCM_BYTES:
            raise ValueError("PCM chunk too large")
        import numpy as np

        sample_rate = int(audio.get("sample_rate") or DEFAULT_PCM_SAMPLE_RATE)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        result = audio_service.analyze(samples, sample_rate=sample_rate)
    except Exception:
        audio["available"] = False
        observation["audio"] = audio
        observation["audio_unavailable"] = True
        return

    audio["available"] = bool(result.get("available", True))
    audio["speech_detected"] = bool(result.get("speech_detected", False))
    audio["speech_probability"] = float(result.get("speech_probability", 0.0))
    audio["rms"] = float(result.get("rms", 0.0))
    audio["voice_band_ratio"] = float(result.get("voice_band_ratio", 0.0))
    audio["duration_seconds"] = float(result.get("duration_seconds", 0.0))
    observation["audio"] = audio
    observation["audio_unavailable"] = not bool(audio["available"])


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
        if len(_last_ingest) > _MAX_TRACKED_SESSIONS:
            cutoff = time.monotonic() - 3600.0
            stale = [sid for sid, ts in _last_ingest.items() if ts < cutoff]
            for sid in stale:
                _last_ingest.pop(sid, None)
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

    # Real audio path FIRST: if the client captured mic PCM, analyze it
    # server-side (pops pcm_data, produces available/speech flags) so the
    # SPEECH/AUDIO_UNAVAILABLE signals come from actual audio data, and so the
    # same results feed build_observation below when a frame is attached.
    _analyze_audio(observation)

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
    trust = result.get("trust") or {}
    return ProctoringSignalOut(
        risk=result.get("risk", {}),
        runs=result.get("runs"),
        repeated=result.get("repeated"),
        incident_candidates=result.get("incident_candidates"),
        trust=TrustOut(
            score=float(trust.get("score", 100.0)),
            level=trust.get("level") or "NORMAL",
            delta=float(trust.get("delta", 0.0)),
            source=trust.get("source") or "baseline",
            reason=trust.get("reason") or "",
        ),
    )