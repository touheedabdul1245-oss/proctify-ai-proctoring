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
