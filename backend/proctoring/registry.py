"""
Shared per-session proctoring engine registry (Stage 5).

The Stage-3 engine is explicitly session-scoped: sustained confirmations,
cooldown gating and repeat tracking only graduate when the SAME ``SessionRisk``
instance lives across API requests. The Stage-3/4 ingest surfaces violated that
contract by rebuilding the engine on every request, so events never confirmed
and incidents never surfaced from live data.

This registry keeps ONE engine per active exam session (bounded, thread-safe)
and drops it once the session closes, so "live" monitoring sees real,
sustained signals without any second architecture — it is the same pure engine
the Stage-3 modules already define.

The registry additionally remembers the last persisted risk level per session
so the API layer only writes a risk_scores snapshot when the band actually
changed (keeping the timeline compact on quiet sessions).
"""
import threading
import time
from typing import Dict, Optional, Tuple

from .engine import SessionRisk, build_engine

REGISTRY_MAX_SESSIONS = 512
_REGISTRY_IDLE_TTL_SECONDS = 12 * 3600.0  # defensive purge; sessions are dropped on close

_lock = threading.Lock()
_entries: Dict[int, Dict[str, object]] = {}


def get_engine(exam_session_id: int) -> Tuple[SessionRisk, Dict[str, object]]:
    """Return (engine, meta) for a session, creating the engine on first use."""
    key = int(exam_session_id)
    with _lock:
        entry = _entries.get(key)
        if entry is None:
            engine = build_engine(exam_session_id=key)
            entry = {"engine": engine, "seen": time.time(),
                     "last_risk_level": None}
            _entries[key] = entry
            if len(_entries) > REGISTRY_MAX_SESSIONS:
                _evict_oldest_locked()
        else:
            entry["seen"] = time.time()
        return entry["engine"], entry


def drop(exam_session_id: int) -> None:
    """Remove a session's engine and metadata (called when the session closes)."""
    with _lock:
        _entries.pop(int(exam_session_id), None)


def clear_all() -> None:
    with _lock:
        _entries.clear()


def purge_idle(max_age_seconds: float = _REGISTRY_IDLE_TTL_SECONDS) -> int:
    """Drop engines not seen for ``max_age_seconds`` (defensive memory bound)."""
    cutoff = time.time() - float(max_age_seconds)
    with _lock:
        stale = [k for k, e in _entries.items() if e.get("seen", 0) < cutoff]
        for k in stale:
            _entries.pop(k, None)
        return len(stale)


def active_count() -> int:
    with _lock:
        return len(_entries)


def _evict_oldest_locked() -> None:
    if not _entries:
        return
    oldest_key = min(_entries, key=lambda k: _entries[k].get("seen", 0))
    _entries.pop(oldest_key, None)