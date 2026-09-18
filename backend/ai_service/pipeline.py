"""
Per-frame AI observation pipeline (Stage 5).

Completes the Stage-3 contract: one decoded camera frame + audio context ->
a single normalized observation dict for the proctoring engine, by running the
EXISTING AI components read-only (YOLO, MediaPipe, PnP, audio). No component is
trained, downloaded or replaced.

Failure handling is graceful by design: if a model cannot load or a frame is
sized/exceeded limits, the pipeline degrades to availability flags so the
engine can emit honest CAMERA_UNAVAILABLE / AUDIO_UNAVAILABLE events instead of
crashing a student's exam. Clients never post frames larger than
``MAX_FRAME_PIXELS`` (the engine/observation layer enforces the same cap).
"""
from typing import Any, Dict, Optional

from .service import ai_service

_MAX_FRAME_PIXELS = 640 * 480


def run_vision_pipeline(frame) -> Dict[str, Any]:
    """Run YOLO + MediaPipe + PnP over one frame -> normalized observation slice.

    Returns:
        {
            "objects": [det...],                  # YOLO (empty on failure)
            "face": {...},                        # MediaPipe (always shaped)
            "head_pose": {...},                   # PnP (on first face with landmarks)
            "camera_available": bool,
            "camera_error": str | None,
        }
    """
    objects: list = []
    face: Dict[str, Any] = {"available": False, "face_count": 0, "faces": [], "error": "no frame"}
    head_pose: Dict[str, Any] = {"available": False, "error": "no face landmarks"}
    camera_available = frame is not None
    camera_error: Optional[str] = None

    if not camera_available:
        return {
            "objects": objects,
            "face": face,
            "head_pose": head_pose,
            "camera_available": False,
            "camera_error": "no frame captured",
        }

    try:
        import numpy as np

        h, w = int(frame.shape[0]), int(frame.shape[1])
        if h * w > _MAX_FRAME_PIXELS:
            return {
                "objects": [],
                "face": {"available": False, "face_count": 0, "faces": [], "error": "frame too large"},
                "head_pose": {"available": False, "error": "frame too large"},
                "camera_available": False,
                "camera_error": "frame too large",
            }
    except Exception:
        return {
            "objects": [],
            "face": {"available": False, "face_count": 0, "faces": [], "error": "invalid frame"},
            "head_pose": {"available": False, "error": "invalid frame"},
            "camera_available": False,
            "camera_error": "invalid frame",
        }

    # --- YOLO object detections (phone / earphone) -------------------------
    try:
        yolo = ai_service.yolo
        if yolo.is_loaded() or yolo.load():
            objects = list(yolo.detect(frame) or [])
    except Exception:
        objects = []

    # --- MediaPipe face landmarks + gaze ------------------------------------
    try:
        mp = ai_service.mediapipe
        if mp.is_loaded() or mp.load():
            raw_face = mp.process(frame) or {}
            if raw_face.get("available"):
                face = {
                    "available": True,
                    "face_count": int(raw_face.get("face_count", 0) or 0),
                    "faces": list(raw_face.get("faces") or []),
                }
            else:
                face = {"available": False, "face_count": 0, "faces": [],
                        "error": raw_face.get("error")}
        else:
            face = {"available": False, "face_count": 0, "faces": [],
                    "error": mp.health().get("error")}
    except Exception as exc:
        face = {"available": False, "face_count": 0, "faces": [], "error": str(exc)}

    # --- PnP head pose from the first face that has landmarks --------------
    try:
        pnp = ai_service.pnp
        if pnp.is_loaded() or pnp.load():
            for f in face.get("faces") or []:
                lms = f.get("landmarks")
                if not lms:
                    continue
                pose = pnp.estimate(lms)
                if pose.get("available"):
                    head_pose = {
                        "available": True,
                        "yaw": pose.get("yaw"),
                        "pitch": pose.get("pitch"),
                        "roll": pose.get("roll"),
                    }
                    break
    except Exception:
        head_pose = {"available": False, "error": "pnp failed"}

    return {
        "objects": objects,
        "face": face,
        "head_pose": head_pose,
        "camera_available": True,
        "camera_error": None,
    }


def build_observation(frame,
                      audio: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Combine vision results + audio context into ONE engine observation dict."""
    obs = run_vision_pipeline(frame)
    audio = audio if isinstance(audio, dict) else {}
    obs["audio"] = {
        "available": bool(obs.get("camera_available", True) and audio.get("available", True)),
        "speech_detected": bool(audio.get("speech_detected", False)),
        "speech_probability": audio.get("speech_probability", 0.0),
    }
    obs["audio_unavailable"] = not bool(obs["audio"]["available"])
    return obs