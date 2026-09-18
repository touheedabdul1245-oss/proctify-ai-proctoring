"""
Event extraction (Stage 3) — turn a raw frame observation + AI backend results
into structured, timestamped EVENT candidates.

This module is PURE: it only interprets what the AI services reported for one
frame. It does not decide anything. Sustained-vs-noise graduation, temporal
cooldowns and repeated-detection handling live in ``temporal.py``.

Contract of an event candidate dict:

    {
        "event_type": EVENT_*,
        "source": "YOLO" | "MEDIAPIPE" | "PNP" | "AUDIO" | "ENGINE",
        "confidence": 0..1,
        "bbox": [x1,y1,x2,y2] | None,
        "details": { ... }          # per-type extra context
    }

A frame where everything is fine yields an empty list — no event at all.
"""
from typing import Any, Dict, List, Optional

from .constants import (
    EVENT_AUDIO_UNAVAILABLE,
    EVENT_CAMERA_UNAVAILABLE,
    EVENT_EARPHONE,
    EVENT_EXTRA_PERSON,
    EVENT_FACE_MISSING,
    EVENT_GAZE_DEVIATION,
    EVENT_HEAD_DEVIATION,
    EVENT_PHONE,
    EVENT_SOURCES,
    EVENT_SPEECH,
)


def _max_conf(detections: List[Dict[str, Any]], class_name: str) -> Optional[Dict[str, Any]]:
    best = None
    for d in detections:
        if d.get("class_name") == class_name:
            if best is None or d.get("confidence", 0) > best.get("confidence", 0):
                best = d
    return best

def _event(event_type: str, confidence: float,
           source: Optional[str] = None,
           bbox: Optional[List[float]] = None,
           details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "source": source or EVENT_SOURCES.get(event_type, "ENGINE"),
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "bbox": list(bbox) if bbox else None,
        "details": dict(details or {}),
    }


def events_from_observation(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map one frame observation + AI results to raw event candidates.

    ``observation`` is the structured dict produced by ai_service for a single
    frame (see ai_service/mediapipe_interface + yolo_service):
      {
        "frame": frame,                      # optional (ignored here — pure)
        "objects": [detection...],           # YOLO
        "face": { "face_count": N, "faces": [...], "available": bool },
        "head_pose": { ... },                # PnP
        "audio": { ... },                    # audio (optional — frame-only)
        "camera_available": bool,
      }
    """
    events: List[Dict[str, Any]] = []

    # --- YOLO object detections (phone / earphone) -------------------------
    for obj in observation.get("objects") or []:
        class_name = obj.get("class_name")
        if class_name == "phone":
            events.append(_event(EVENT_PHONE, obj.get("confidence", 0.9)))
            # keep the single best per class? bbox:
            idx = None
        elif class_name == "earphone" or class_name == "earphone":
            events.append(_event(EVENT_EARPHONE, obj.get("confidence", 0.9)))
    # dedupe: keep the highest-confidence phone/earphone event only
    events = _dedupe(events)

    # --- MediaPipe face analysis -------------------------------------------
    face = observation.get("face") or {}
    face_avail = bool(face.get("available", True))
    face_count = int(face.get("face_count", 0) or 0)
    faces = face.get("faces") or []

    if not observation.get("camera_available", True):
        events.append(_event(EVENT_CAMERA_UNAVAILABLE, 1.0, source="ENGINE"))
    elif not face_avail:
        events.append(_event(EVENT_CAMERA_UNAVAILABLE, 0.6, source="ENGINE"))
    else:
        if face_count == 0:
            events.append(_event(EVENT_FACE_MISSING, 0.7))
        elif face_count > 1:
            events.append(_event(EVENT_EXTRA_PERSON, 0.85, bbox=faces[1].get("bbox")))

        for f in faces:
            gaze = f.get("gaze") or {}
            if gaze.get("iris_visible") and (
                abs(gaze.get("x", 0.0)) > 0.34 or abs(gaze.get("y", 0.0)) > 0.30
            ):
                events.append(_event(EVENT_GAZE_DEVIATION, 0.7, bbox=f.get("bbox")))

    # --- PnP head pose ------------------------------------------------------
    pose = observation.get("head_pose") or {}
    if pose.get("available"):
        yaw = abs(float(pose.get("yaw", 0.0)))
        pitch = abs(float(pose.get("pitch", 0.0)))
        if yaw > 28.0 or pitch > 24.0:
            events.append(_event(EVENT_HEAD_DEVIATION, 0.6))

    # --- Audio / speech -----------------------------------------------------
    audio = observation.get("audio") or {}
    if observation.get("audio_unavailable") or not audio.get("available", True):
        events.append(_event(EVENT_AUDIO_UNAVAILABLE, 1.0, source="ENGINE"))
    elif audio.get("speech_detected"):
        events.append(_event(EVENT_SPEECH, audio.get("speech_probability", 0.7)))

    return events


def _dedupe(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the single highest-confidence event per event_type (per frame)."""
    best: Dict[str, Dict[str, Any]] = {}
    for e in events:
        cur = best.get(e["event_type"])
        if cur is None or e.get("confidence", 0) > cur.get("confidence", 0):
            best[e["event_type"]] = e
    # Preserve stable order of first appearance.
    ordered = []
    seen = set()
    for e in events:
        if e["event_type"] not in seen:
            ordered.append(best[e["event_type"]])
            seen.add(e["event_type"])
    return ordered


def test_simulated_observation() -> Dict[str, Any]:
    """A deterministic, deterministic-simulated frame for tests."""
    return {
        "objects": [{
            "class_name": "phone", "class_id": 1, "confidence": 0.93,
            "bbox": [30, 45, 120, 140],
        }],
        "face": {
            "available": True,
            "face_count": 2,
            "faces": [
                {"bbox": [0.1, 0.1, 0.4, 0.6], "gaze": {"x": 0.0, "y": 0.0, "iris_visible": True}},
                {"bbox": [0.6, 0.3, 0.9, 0.8], "gaze": {"x": -0.5, "y": 0.2, "iris_visible": True}},
            ],
        },
        "head_pose": {"available": True, "yaw": 35.0, "pitch": 5.0},
        "audio": {"available": True, "speech_detected": True, "speech_probability": 0.72},
        "camera_available": True,
        "audio_unavailable": False,
    }
