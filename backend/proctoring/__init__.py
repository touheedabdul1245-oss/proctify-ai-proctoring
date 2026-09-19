"""
``backend.proctoring`` -- Stage-3 proctoring signal engine.

A pure, model-free core that turns one decoded frame + camera/audio
availability flags into structured, timestamped proctoring signals:

    observation -> events (extraction)
        -> temporal (sustained graduation + repeat cooldowns)
        -> incidents (repeated-run candidates for human teacher review)
        -> risk    (banded feature index with hysteresis, never auto-verdict)
        -> evidence (optional image/audio snapshots worth keeping)

This package has NO neural-net dependency and NO file I/O for its pure core,
so it is trivially unit-testable and regression-safe.

Public surface (import * from backend.proctoring):
    bands_contract()            -- risk band contract (automatic, hysteresis-free view)
    build_engine(...)           -- per-exam-session risk orchestrator
    session_risk(...)           -- convenience alias for build_engine
    build_simulated_observation -- deterministic synthetic frame (sim/tests)
    CooldownGate / SessionRisk / RiskState -- types
"""
from .constants import (
    COOLDOWN_BY_FAMILY,
    INCIDENT_BY_EVENT,
    INCIDENT_MIN_RUNS,
    INCIDENT_MIN_RUNS_BY_FAMILY,
    RISK_LABELS,
    RISK_WEIGHTS,
    SIMULATE_ALLOWED,
)
from .events import events_from_observation
from .observation import Observation, decode_data_url, from_frame
from .temporal import CooldownGate
from .incidents import IncidentBuilder, incident_builder
from .risk import RiskState, bands_contract, build_risk_state
from .evidence import store_audio, store_image
from .engine import (
    INGEST_SIMULATE_ALLOWED,
    SessionRisk,
    build_engine,
    build_simulated_observation,
    simulate_allowed,
    stream_from_observation,
    stream_frame,
)

# Re-exported risk helpers so importers need one anchor.
build_risk_state = build_risk_state
feature_index = risk.feature_index if True else risk.feature_index
move_state = risk.move_state
RiskState = RiskState

from . import risk  # noqa: E402  (needed for feature_index / move_state)

IO_DECODE_DATA_URL = decode_data_url  # aliased for route-layer import safety

__all__ = [
    "COOLDOWN_BY_FAMILY",
    "INCIDENT_BY_EVENT",
    "INCIDENT_MIN_RUNS",
    "INCIDENT_MIN_RUNS_BY_FAMILY",
    "RISK_LABELS",
    "RISK_WEIGHTS",
    "SIMULATE_ALLOWED",
    "CooldownGate",
    "IncidentBuilder",
    "IncidentRiskState",
    "Observation",
    "RiskState",
    "SessionRisk",
    "bands_contract",
    "build_engine",
    "build_risk_state",
    "build_simulated_observation",
    "decode_data_url",
    "events_from_observation",
    "from_frame",
    "incident_builder",
    "risk",
    "session_risk",
    "simulate_allowed",
    "store_audio",
    "store_image",
    "stream_frame",
    "stream_from_observation",
]
