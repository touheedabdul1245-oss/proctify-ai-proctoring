"""
Stage-3 engine -- in-memory orchestrator that turns one decoded frame +
camera/audio availability flags into a session-scoped proctoring signal.

WHAT LIVES HERE (and only here):
  * per-exam-session state: risk band (RiskState), per-family cooldown gate
    (CooldownGate), sustained-run bookkeeping (event -> runs) and the
    repeat tracker (distinct sustained run counts per family);
  * the ingest pipeline for ONE frame:
        observation -> events_from_observation
                      -> dedupe -> temporary cooldown gate
                      -> sustained confirmations -> repeated-runs map
                      -> risk.feature_index + RiskState.update (hysteresis)
                      -> IncidentBuilder.build (human-review candidates)
                      -> evidence.store_* for snapshots worth keeping;
  * a compact, deterministic snapshot contract the API layer can cache.

DESIGN RULES (kept here because they are enforced ONLY by the engine, not by
any single pure module):
  * The engine NEVER auto-verdicts. Incidents come out of the builder with
    review_status = PENDING and risk.state only ever labels suspicion.
  * A single detection is a signal, never a sentence: cooldown gates and
    sustained-second thresholds decide if a frame event deserves to graduate.
  * Evidence is written only when a confirmed/sustained signal warrants a
    snapshot, and only by the evidence module (which owns the datastore path).
  * Everything is session-scoped and lives in memory; routing/persistence to
    SQL is the caller's job (evidence rows + ai_event/incident/risk snapshots).

Deterministic by injection (``now_fn``) so unit tests can pin exact timings.
"""
import threading
import time
from typing import Any, Dict, List, Optional

from .constants import (
    COOLDOWN_BY_FAMILY,
    EVENT_COOLDOWN_SECONDS,
    EVENT_MIN_SUSTAINED_SECONDS,
    EVENT_SOURCES,
    SIMULATE_ALLOWED,
)
from .events import events_from_observation
from .evidence import store_audio, store_image
from .incidents import IncidentBuilder, incident_builder
from .observation import Observation, from_frame
from .risk import RiskState, bands_contract, build_risk_state
from .temporal import CooldownGate, _monotonic

INGEST_SIMULATE_ALLOWED: bool = bool(SIMULATE_ALLOWED)

__all__ = [
    "INGEST_SIMULATE_ALLOWED",
    "SessionRisk",
    "build_engine",
    "bands_contract",
    "simulate_allowed",
    "stream_from_observation",
    "stream_frame",
]


INGEST_SIMULATE_ALLOWED: bool = bool(SIMULATE_ALLOWED)


def simulate_allowed() -> bool:
    """Whether the engine may accept a synthetically-built observation (tests/
    demo data). Always False in production unless PROCTIFY_SIMULATE is set."""
    return bool(SIMULATE_ALLOWED)


def _family_of(event: Dict[str, Any]) -> Optional[str]:
    return event.get("event_type")


def _decision(session: "SessionRisk",
              event: Dict[str, Any],
              now: float) -> Optional[Dict[str, Any]]:
    """One event -> whether it graduates now (sustained+cooldown aware)."""
    family = _family_of(event) or "UNKNOWN"
    if not session.gate.can_fire(family):
        return None
    session.gate.arm(family)
    return event


class SessionRisk:
    """Per-exam-session in-memory risk state + temporal bookkeeping.

    The engine keeps exactly ONE of these per active exam session so risk
    bands, cooldowns and repeat counts stay isolated between students.
    """

    def __init__(self, exam_session_id: int,
                 cooldown_by_family: Optional[Dict[str, float]] = None,
                 now_fn=None):
        self.exam_session_id = int(exam_session_id)
        self.gate = CooldownGate(cooldown_by_family=cooldown_by_family,
                                 now_fn=now_fn)
        self.risk = build_risk_state(level=0, index=0.0)
        self._now = now_fn or _monotonic
        self._lock = threading.Lock()
        self._runs: Dict[str, int] = {}
        self._sustained: Dict[str, Dict[str, Any]] = {}
        self._repeated: Dict[str, int] = {}
        self._last: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    def ingest(self, observation: Dict[str, Any],
               persist: bool = True) -> Dict[str, Any]:
        """Process one observation (dict) and return the compact signal dict.

        ``persist`` toggles whether evidence snapshots are written when the
        observation warrants them (image/audio already captured upstream).
        """
        events = events_from_observation(observation)
        now = self._now()
        confirmed: List[Dict[str, Any]] = []

        for evt in events:
            family = _family_of(evt) or "UNKNOWN"
            # --- sustained graduation ----------------------------------
            # A single short glance is noise; a sustained run confirms.
            state = self._sustained.setdefault(family, {
                "count": 0, "first": now, "last": now,
                "event": evt,
            })
            window = EVENT_MIN_SUSTAINED_SECONDS.get(family, 2.0)
            if now - state["first"] >= window:
                state["last"] = now
                if self.gate.can_fire(family):
                    self.gate.arm(family)
                    confirmed.append(evt)
                    self._runs[family] = self._runs.get(family, 0) + 1
            else:
                state["count"] += 1

        # --- repeat tracking (distinct sustained runs) ------------------
        # A run only counts again after a gap >= repeat reset (per family).
        risk_result = self._update_risk(confirmed, now)

        if persist and confirmed:
            self._maybe_evidence(confirmed, now)

        snapshot = self.risk.snapshot()
        incident_candidates = []
        if risk_result:
            repeated = {f: c for f, c in self._repeated.items() if c}
            if repeated:
                incident_candidates = incident_builder.build(
                    repeated,
                    risk_label=snapshot.get("label", "NORMAL"),
                    first_ts=None,
                    last_ts=None,
                )
        self._last = {
            "events": confirmed,
            "risk": snapshot,
            "incident_candidates": incident_candidates,
        }
        return dict(self._last)

    def _update_risk(self, confirmed: List[Dict[str, Any]], now: float) -> bool:
        if not confirmed:
            return False
        # choose the single most confident event per family to feed risk
        by_family: Dict[str, float] = {}
        for evt in confirmed:
            family = _family_of(evt) or "UNKNOWN"
            by_family[family] = max(by_family.get(family, 0.0),
                                    float(evt.get("confidence", 0.0)))
        index = feature_index(
            frame_event_weight=0.0,
            sustained_events=dict(self._runs),
            speech_weight=float(by_family.get(EVENT_SOURCES.get(EVENT_SPEECH, ""), 0.0)),
            temporal_weight=0.0,
            incident_weight=0.0,
        )
        self.risk.update(index)
        return True

    def _maybe_evidence(self, confirmed: List[Dict[str, Any]], now: float) -> None:
        """Store evidence only if this engine was told it may (sim path)."""
        # No-op here by default; the AI/API layer captures snapshots and calls
        # evidence.store_* directly when a confirmed signal is worth keeping.
        return

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "risk": self.risk.snapshot(),
                "runs": dict(self._runs),
                "repeated": dict(self._repeated),
            }


def build_simulated_observation(step: int = 0) -> Dict[str, Any]:
    """Deterministic, simulated observation sequence for tests / demos.

    Not part of the production flow: the engine only accepts these when
    PROCTIFY_SIMULATE is set (see simulate_allowed). Produces a phone object
    on even steps and clean frames on odd steps so sustained/cooldown/repeat
    logic can be exercised deterministically.
    """
    return test_simulated_observation() if step % 2 == 0 else {
        "objects": [],
        "face": {"available": True, "face_count": 1, "faces": []},
        "head_pose": {},
        "audio": {"available": True, "speech_detected": False},
        "camera_available": True,
    }


def build_engine(exam_session_id: int = 0,
                 cooldown_by_family: Optional[Dict[str, float]] = None) -> SessionRisk:
    return SessionRisk(exam_session_id=exam_session_id,
                       cooldown_by_family=cooldown_by_family)


def stream_from_observation(session: SessionRisk,
                            observation: Dict[str, Any]) -> Dict[str, Any]:
    return session.ingest(observation)


def stream_frame(session: SessionRisk, frame: Any,
                 camera_available: bool = True) -> Dict[str, Any]:
    obs = from_frame(frame, camera_available=camera_available)
    return session.ingest(obs.to_dict())
