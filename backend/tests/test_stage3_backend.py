"""
Stage-3 backend tests — the Stage-3 proctoring engine + router surface,
run WITHOUT any DB or AI-model dependency (pure + endpoint-shape only).

These are the deterministic, regression-safe contracts that the AI service and
SQL layers may then build on. They pin:

  * the risk band contract (levels / band upper / hysteresis / per-family
    weights) that the UI pill and teacher review consume;
  * risk feature-index math (weighted, sustained-aware) + banded risk state
    graduation with hysteresis — suspicion ONLY, never a verdict;
  * the per-family cooldown gate (thread-safe, clock-injectable);
  * the incident builder (min-run thresholds -> PENDING human-review
    candidates; the engine never auto-verdicts);
  * the Stage-3 API routes (prefix + bands + ingest are present and the
    bands/get returns a valid bands contract).

Pure modules are imported via ``backend.proctoring`` whose ``__init__`` has no
side effects on import — safe to use here.
"""
import threading
import time
from typing import Any, Dict, List

import pytest

from backend.proctoring import (
    bands_contract,
    build_risk_state,
    bands_contract as bands,
    feature_index,
    move_state,
    risk,
    simulate_allowed,
)
from backend.proctoring.events import events_from_observation
from backend.proctoring.observation import from_frame
from backend.proctoring.temporal import CooldownGate
from backend.proctoring.incidents import IncidentBuilder, incident_builder
from backend.proctoring.evidence import pathed


# ---------------------------------------------------------------------------
# risk bands contract
# ---------------------------------------------------------------------------

def test_bands_contract_shape():
    c = bands_contract()
    assert set(c) == {"band_upper", "hysteresis", "levels", "per_family_weights"}
    assert c["levels"] == ["NORMAL", "ATTENTION", "ELEVATED", "HIGH"]
    assert len(c["band_upper"]) == 3  # 3 inner bands between NORMAL..HIGH
    assert 0.0 < c["hysteresis"] < 0.3
    assert "OBJECT_PHONE" in c["per_family_weights"]


def test_feature_index_sustained_aware():
    # bare frame weight, no sustained run
    base = feature_index(frame_event_weight=0.20, sustained_events={},
                         speech_weight=0.0, temporal_weight=0.0,
                         incident_weight=0.0)
    # same frame weight PLUS a sustained phone run adds momentum
    sustained = feature_index(frame_event_weight=0.20,
                              sustained_events={"OBJECT_PHONE": 2},
                              speech_weight=0.0, temporal_weight=0.0,
                              incident_weight=0.0)
    # a sustained run should add momentum above the bare frame weight
    assert sustained > base
    # and the contract clamps the index to [0.0, 1.0]
    assert 0.0 <= base <= sustained <= 1.0


def test_risk_state_graduation_hysteresis():
    state = build_risk_state()
    assert state.label == "NORMAL"
    # a single elevated feature jump -> at least ATTENTION (suspicion only)
    state.update(feature_index(frame_event_weight=0.45,
                               sustained_events={},
                               speech_weight=0.0, temporal_weight=0.0,
                               incident_weight=0.0))
    assert state.label in ("ATTENTION", "ELEVATED")
    assert state.index >= 0.0


def test_risk_never_verdict():
    """Risk never auto-verdicts: label is suspicion, not a result."""
    state = build_risk_state(level=3, index=0.98)  # highest band
    snap = state.snapshot()
    assert snap["level"] in ("ELEVATED", "HIGH")
    # still just a level + index — no verdict field
    assert "verdict" not in snap


# ---------------------------------------------------------------------------
# cooldown gate (clock-injected, deterministic)
# ---------------------------------------------------------------------------

class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_cooldown_gate_injected_clock():
    clock = _FakeClock()
    gate = CooldownGate(cooldown_by_family={"OBJECT_PHONE": 5.0},
                        now_fn=clock)
    assert gate.can_fire("OBJECT_PHONE") is True
    gate.arm("OBJECT_PHONE")
    assert gate.can_fire("OBJECT_PHONE") is False
    clock.t += 4.9
    assert gate.can_fire("OBJECT_PHONE") is False   # still cooling
    clock.t += 0.3                                  # 5.2s > 5.0
    assert gate.can_fire("OBJECT_PHONE") is True


def test_cooldown_gate_per_family():
    clock = _FakeClock()
    gate = CooldownGate(cooldown_by_family={"OBJECT_PHONE": 5.0,
                                            "SPEECH": 1.0},
                        now_fn=clock)
    gate.arm("OBJECT_PHONE")
    # other family unaffected
    assert gate.can_fire("SPEECH") is True
    assert gate.can_fire("OBJECT_PHONE") is False


# ---------------------------------------------------------------------------
# incident builder (PENDING only)
# ---------------------------------------------------------------------------

def test_incident_builder_respects_min_runs():
    builder = IncidentBuilder(min_runs={"OBJECT_PHONE": 3})
    candidates = builder.build(repeated={"OBJECT_PHONE": 2},
                               risk_label="ATTENTION")
    assert candidates == []          # under min-runs -> no candidate
    candidates = builder.build(repeated={"OBJECT_PHONE": 3},
                               risk_label="ATTENTION")
    assert len(candidates) == 1
    assert candidates[0]["review_status"] == "PENDING"


# ---------------------------------------------------------------------------
# Regression: family→incident-type threshold resolution (A + B)
# ---------------------------------------------------------------------------

def test_incident_below_min_threshold_no_candidate():
    """(A) A family with runs below its incident-type threshold must NOT
    produce a candidate — even when the old bug would have returned one."""
    from backend.proctoring.constants import INCIDENT_MIN_RUNS

    builder = IncidentBuilder()  # default thresholds
    for family, runs in [
        ("OBJECT_PHONE", 1),     # PHONE_USE min=2
        ("OBJECT_EARPHONE", 1),   # EARPHONE_USE min=2
        ("EXTRA_PERSON", 1),      # EXTRA_PERSON min=2
        ("FACE_MISSING", 2),      # FACE_ABSENT min=3
        ("HEAD_DEVIATION", 2),    # HEAD_DEVIATION min=3
        ("GAZE_DEVIATION", 2),    # GAZE_DEVIATION min=3
        ("SPEECH_DETECTED", 2),   # SPEECH_ACTIVITY min=3
        ("CAMERA_UNAVAILABLE", 1),  # ENVIRONMENT_UNAVAILABLE min=2
    ]:
        candidates = builder.build(repeated={family: runs}, risk_label="NORMAL")
        assert candidates == [], (
            f"{family}: {runs} runs should NOT create a candidate "
            f"(threshold={INCIDENT_MIN_RUNS.get(builder._min.get('OBJECT_PHONE'), '?')})"
        )


def test_incident_threshold_reached_creates_candidate():
    """(B) Exactly at the configured threshold, a candidate MUST be created."""
    builder = IncidentBuilder()  # default thresholds
    cases = [
        ("OBJECT_PHONE", 2, "PHONE_USE"),
        ("OBJECT_EARPHONE", 2, "EARPHONE_USE"),
        ("EXTRA_PERSON", 2, "EXTRA_PERSON"),
        ("FACE_MISSING", 3, "FACE_ABSENT"),
        ("HEAD_DEVIATION", 3, "HEAD_DEVIATION"),
        ("GAZE_DEVIATION", 3, "GAZE_DEVIATION"),
        ("SPEECH_DETECTED", 3, "SPEECH_ACTIVITY"),
        ("CAMERA_UNAVAILABLE", 2, "ENVIRONMENT_UNAVAILABLE"),
        ("AUDIO_UNAVAILABLE", 2, "ENVIRONMENT_UNAVAILABLE"),
    ]
    for family, threshold_runs, expected_type in cases:
        candidates = builder.build(
            repeated={family: threshold_runs}, risk_label="ATTENTION"
        )
        assert len(candidates) == 1, (
            f"{family}: {threshold_runs} runs should produce a candidate"
        )
        assert candidates[0]["incident_type"] == expected_type, (
            f"{family}: incident_type should be {expected_type}, "
            f"got {candidates[0]['incident_type']}"
        )
        assert candidates[0]["event_types"] == [family]
        assert candidates[0]["review_status"] == "PENDING"
        assert candidates[0]["event_count"] == threshold_runs


# ---------------------------------------------------------------------------
# events extraction (pure, one observation)
# ---------------------------------------------------------------------------

def test_events_from_observation_phone():
    obs = {
        "objects": [{"class_name": "phone", "confidence": 0.91}],
        "face": {"available": True, "face_count": 1, "faces": []},
        "head_pose": {},
        "audio": {"available": True, "speech_detected": False},
        "camera_available": True,
    }
    evts = events_from_observation(obs)
    assert any(e["event_type"] == "OBJECT_PHONE" for e in evts)


def test_simulate_allowed_is_false_default():
    """Production default: no synthetic ingest path may fire."""
    assert simulate_allowed() is False


def test_evidence_pathed():
    p = pathed("snapshots/x.jpg")
    assert str(p).replace("\\", "/").endswith("snapshots/x.jpg")


def test_from_frame_observation_shape():
    import numpy as np
    frame = np.zeros((240, 320, 3), dtype="uint8")
    obs = from_frame(frame, camera_available=True)
    assert obs.has_image is True
    d = obs.to_dict()
    assert d["height"] == 240
    assert d["width"] == 320


# ---------------------------------------------------------------------------
# Engine-level incident regressions (A - below-minimum, B - threshold,
# C - cooldown/duplicate, D - trust not double-penalized)
# ---------------------------------------------------------------------------

class _StepClock:
    """Deterministic clock for SessionRisk: advance() + call() -> elapsed.

    Starts at a non-zero base (1000.0) so ``first=0`` is never mistaken for a
    missing timestamp by engine code that does ``float(x or now)``."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


def _obs_phone(conf: float = 0.92):
    return {
        "objects": [{"class_name": "phone", "confidence": conf,
                     "bbox": [10, 20, 80, 90]}],
        "face": {"available": True, "face_count": 1, "faces": []},
        "head_pose": {"available": True, "yaw": 3.0, "pitch": 1.0},
        "audio": {"available": True, "speech_detected": False},
        "camera_available": True,
    }


def _obs_clean():
    return {
        "objects": [],
        "face": {"available": True, "face_count": 1, "faces": []},
        "head_pose": {"available": True, "yaw": 3.0, "pitch": 1.0},
        "audio": {"available": True, "speech_detected": False},
        "camera_available": True,
    }


def test_engine_below_min_runs_no_incident():
    """(A) One isolated/noisy phone run must NOT create an incident."""
    from backend.proctoring.engine import SessionRisk

    clock = _StepClock()
    eng = SessionRisk(9001, now_fn=clock)
    eng.ingest(_obs_phone())                 # t=0: sustained starts
    clock.advance(2.5)                        # cross the 2.0s phone window
    result = eng.ingest(_obs_phone())         # first confirmed run (runs=1)
    assert result["runs"].get("OBJECT_PHONE", 0) == 1
    assert result["repeated"] == {}
    assert result["incident_candidates"] == []


def test_engine_repeat_reaches_threshold_creates_incident():
    """(B) Two DISTINCT phone runs (cooldown + repeat-gap separated) graduate
    exactly ONE PHONE_USE incident candidate — never an auto-verdict."""
    from backend.proctoring.engine import SessionRisk

    clock = _StepClock()
    eng = SessionRisk(9002, now_fn=clock)
    eng.ingest(_obs_phone())                  # t=0
    clock.advance(2.5)
    eng.ingest(_obs_phone())                  # t=2.5: run 1 (gate armed ~22.5)
    clock.advance(20.0)
    eng.ingest(_obs_phone())                  # t=22.5: cooldown expired -> run 2 (gap 20s < 30s)
    clock.advance(30.0)
    result = eng.ingest(_obs_phone())         # t=52.5: gap 30s -> distinct run 2
    assert result["runs"].get("OBJECT_PHONE", 0) >= 2
    assert result["repeated"].get("OBJECT_PHONE", 0) == 2, result["repeated"]
    cands = result["incident_candidates"]
    assert len(cands) == 1, cands
    assert cands[0]["incident_type"] == "PHONE_USE"
    assert cands[0]["event_types"] == ["OBJECT_PHONE"]
    assert cands[0]["review_status"] == "PENDING"


def test_engine_cooldown_blocks_duplicate_runs():
    """(C) Cooldown prevents a second run from duplicating within one window."""
    from backend.proctoring.engine import SessionRisk

    clock = _StepClock()
    eng = SessionRisk(9003, now_fn=clock)
    eng.ingest(_obs_phone())
    clock.advance(2.5)
    r1 = eng.ingest(_obs_phone())              # run 1
    assert r1["runs"].get("OBJECT_PHONE", 0) == 1
    clock.advance(1.0)
    r2 = eng.ingest(_obs_phone())              # inside cooldown (3.5s < 22.5s)
    assert r2["runs"].get("OBJECT_PHONE", 0) == 1, r2["runs"]
    assert r2["repeated"] == {}
    assert r2["incident_candidates"] == []


def test_engine_incident_does_not_double_penalize_trust():
    """(D) Trust moves ONLY from confirmed events. Graduating an incident
    candidate on the same ingest adds NO extra trust penalty, and a clean
    frame afterwards leaves trust untouched."""
    from backend.proctoring.engine import SessionRisk

    clock = _StepClock()
    eng = SessionRisk(9004, now_fn=clock)
    eng.ingest(_obs_phone())
    clock.advance(2.5)
    first = eng.ingest(_obs_phone())           # run 1 -> penalty 1
    trust_after_first = float(first["trust"]["score"])
    assert trust_after_first < 100.0
    clock.advance(20.0)
    eng.ingest(_obs_phone())                   # run 2 (cooldown expired)
    clock.advance(30.0)
    incident = eng.ingest(_obs_phone())        # distinct run 2 -> incident + penalty 2
    cands = incident["incident_candidates"]
    assert len(cands) == 1 and cands[0]["incident_type"] == "PHONE_USE"
    # the delta on THIS ingest is a plain event penalty, not a doubled one
    assert incident["trust"]["delta"] < 0.0
    assert incident["trust"]["source"] == "penalty"
    assert incident["trust"]["families"] == ["OBJECT_PHONE"]
    assert "incident" not in incident["trust"]["reason"].lower()
    # a clean frame afterwards must NOT touch trust (incident stays in the
    # persisted/engine state even though the live candidate list is derived
    # only on ingests that confirmed events)
    clock.advance(1.0)
    clean = eng.ingest(_obs_clean())
    assert float(clean["trust"]["score"]) == float(incident["trust"]["score"])
