"""
Risk evaluation (Stage 3) — probability-bridge index -> banded label.

DESIGN RULES (hard):
  * ``index`` is a weighted *feature vector* sum of active signals, decayed over
    time (half-life). It is NOT "100 minus penalty points", and a single event
    never multiplies it.
  * The human-facing label comes from BANDS with HYSTERESIS: moving up requires
    crossing an upper band edge; moving back down requires crossing a lower band
    edge plus a margin (``RISK_HYSTERESIS``). This prevents label flicker.
  * Presence of high-malpractice incidents only RAISES suspicion; it never
    auto-verdicts the student. ``review_status`` remains PENDING.

The engine keeps a per-session risk STATE (level + index + last factors). It is
purely in-memory and temporal (see temporal.py); RNA for persistence lives in
engine.py. Everything here is deterministic and unit-testable.

    assess(feature_index) -> {"level": RISK_LABEL_*, "index": float}
    move_state(current, feature_index) -> new state (hysteresis-aware)
"""
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    RISK_BAND_UPPER,
    RISK_HYSTERESIS,
    RISK_LABELS,
    RISK_WEIGHTS,
)


def feature_index(frame_event_weight: float = 0.0,
                  sustained_events: Optional[Dict[str, int]] = None,
                  speech_weight: float = 0.0,
                  temporal_weight: float = 0.0,
                  incident_weight: float = 0.0) -> float:
    """Weighted feature vector -> risk index (0.. high, unbounded upward).

    Each contribution is bounded (0..1) and combined additively with fixed
    weights; a SINGLE event can move the index by at most one weight, so any
    single glance is a signal, never a sentence.
    """
    contribs = [
        min(1.0, float(frame_event_weight or 0.0)) * 1.0,  # per-frame events
    ]
    for family, runs in (sustained_events or {}).items():
        weight = RISK_WEIGHTS.get(family, 0.10)
        # runs accumulate slowly; cap each family so one family cannot saturate.
        contribs.append(min(float(runs or 0), 6.0) * weight)
    contribs.append(min(1.0, float(speech_weight or 0.0)) * 0.35)
    contribs.append(min(1.0, float(temporal_weight or 0.0)))
    contribs.append(min(1.0, float(incident_weight or 0.0)) * 0.90)
    return round(float(sum(contribs)), 4)


def _level_for_bands(index: float, upper: Tuple[float, ...]) -> tuple:
    """Map an index to (level_index, band_upper) using band edges."""
    for i, u in enumerate(upper):
        if index <= u:
            return i, u
    return len(upper), float("inf")


def move_state(level_index: int, index: float) -> int:
    """Hysteresis-aware band move given current level index (0..3)."""
    current_upper = RISK_BAND_UPPER[level_index] if level_index < len(RISK_BAND_UPPER) else RISK_BAND_UPPER[-1]
    if level_index > 0 and index <= RISK_BAND_UPPER[level_index - 1] - RISK_HYSTERESIS:
        return level_index - 1
    if index > current_upper + RISK_HYSTERESIS:
        return min(level_index + 1, len(RISK_BAND_UPPER))
    return level_index


class RiskState:
    """Per-session risk memory: current band + feature index + factor log."""

    __slots__ = ("level", "index", "_last_factors")

    def __init__(self, level: int = 0, index: float = 0.0):
        self.level = int(level)
        self.index = round(float(index), 4)
        self._last_factors: List[Dict[str, Any]] = []

    @property
    def label(self) -> str:
        return RISK_LABELS[min(self.level, len(RISK_LABELS) - 1)]

    def update(self, index: float, factors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        nxt = move_state(self.level, index)
        self.level = nxt
        self.index = round(float(index), 4)
        if factors is not None:
            self._last_factors = list(factors or [])
        return {
            "level": self.label,
            "index": self.index,
            "level_index": self.level,
            "factors": list(self._last_factors),
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "level": self.label,
            "index": self.index,
            "level_index": self.level,
            "factors": list(self._last_factors),
        }


def build_risk_state(level: int = 0, index: float = 0.0) -> RiskState:
    return RiskState(level=level, index=index)


def bands_contract() -> Dict[str, Any]:
    """Expose the band / hysteresis contract for UIs & docs."""
    return {
        "levels": list(RISK_LABELS),
        "band_upper": list(RISK_BAND_UPPER),
        "hysteresis": RISK_HYSTERESIS,
        "per_family_weights": dict(RISK_WEIGHTS),
    }
