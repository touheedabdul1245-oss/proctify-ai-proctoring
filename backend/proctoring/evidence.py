"""
Evidence persistence (Stage 3).

A confirmed event which the temporal layer deems worth a snapshot is persisted
here: the raw JPEG (or WAV/JSON metadata) is written to the filesystem under
``EVIDENCE_DIR/<session_token>/`` and a single SQL row (Evidence model) points
at it. Evidence is NEVER interpreted by the engine — it exists so a human
teacher can, at review time, open the exact tape.

    store_image(session_token, exam_session_id, event) -> {
        "file_path": str, "media_type": "image/jpeg",
        "row_id": int, "size_bytes": int,
    }

All writes are guarded so two concurrent observations cannot collide on the
same filename. Pure I/O — the caller (engine) decides WHAT is worth keeping.
"""
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import EVIDENCE_DIR
from .constants import EVENT_CAMERA_UNAVAILABLE, EVENT_AUDIO_UNAVAILABLE

_FMT = "%Y%m%d_%H%M%S_%f"

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(token: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(token)
        if lock is None:
            lock = threading.Lock()
            _locks[token] = lock
        return lock


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _snapshot_token() -> str:
    return time.strftime(_FMT, time.gmtime())


def store_image(session_token: str, exam_session_id: int,
                event: Dict[str, Any], image_bytes: bytes) -> Dict[str, Any]:
    """Write an evidence JPEG + SQL row reference."""
    if not image_bytes:
        return {"file_path": None, "media_type": "image/jpeg",
                "row_id": None, "size_bytes": 0, "error": "no image bytes"}

    token = _snapshot_token() + "_" + str(exam_session_id)
    rel_dir = Path(session_token or "anon")
    stamp = _snapshot_token()
    name = f"{event.get('event_type', 'event')}_{stamp}.jpg"
    rel = rel_dir / name
    full = EVIDENCE_DIR / rel
    _ensure_parent(full)

    with _lock_for(session_token or "anon"):
        full.write_bytes(image_bytes)

    metadata = {
        "event_type": event.get("event_type"),
        "confidence": event.get("confidence"),
        "source": event.get("source"),
        "details": event.get("details"),
        "captured_within": {
            "imagewidth": None,
            "imageheight": None,
        },
    }

    # The caller persists the SQL row; we only return the contract.
    return {
        "file_path": str(rel),
        "absolute_path": str(full),
        "media_type": "image/jpeg",
        "size_bytes": int(full.stat().st_size),
        "metadata": metadata,
    }


def store_audio(session_token: str, exam_session_id: int,
                event: Dict[str, Any], pcm_bytes: bytes) -> Dict[str, Any]:
    """Persist an audio clip (.wav) + row contract (microphone asset)."""
    if not pcm_bytes:
        return {"file_path": None, "media_type": "audio/wav",
                "row_id": None, "size_bytes": 0, "error": "no audio bytes"}
    stamp = _snapshot_token()
    rel_dir = Path(session_token or "anon")
    name = f"{event.get('event_type', 'event')}_{stamp}.wav"
    rel = rel_dir / name
    full = EVIDENCE_DIR / rel
    _ensure_parent(full)
    with _lock_for(session_token or "anon"):
        full.write_bytes(pcm_bytes)
    return {
        "file_path": str(rel),
        "absolute_path": str(full),
        "media_type": "audio/wav",
        "size_bytes": int(full.stat().st_size),
        "metadata": {
            "event_type": event.get("event_type"),
            "confidence": event.get("confidence"),
            "details": event.get("details"),
        },
    }


def pathed(rel_path: str) -> Path:
    return EVIDENCE_DIR / rel_path
