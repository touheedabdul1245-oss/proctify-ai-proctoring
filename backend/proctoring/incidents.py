"""
Incident candidates (Stage 3) — pattern promotion from confirmed events.

Runs *after* the temporal layer has confirmed sustained events. The job here is
to recognise that a pattern is worth a TEACHER'S attention — nothing more.

Rules honoured:
  * A confirmed incident candidate is NEVER an auto-verdict. It is created with
    ``review_status = PENDING`` and exists only so a human teacher can review it.
  * Repeat detection never depends on a single suspicious glance — the temporal
    engine counts DISTINCT sustained runs (see temporal.RepeatTracker), and only
    teams of repeated runs graduate into an incident candidate (INCIDENT_MIN_*).
  * The engine NEVER marks a student as "caught" — it surfaces review work.

Incident candidate (dict) contract::

    {
        "incident_type": INCIDENT_*,
        "risk_level": RISK_LABEL_*,          # state when created
        "confidence": 0..1,
        "event_count": int,
        "event_types": [EVENT_*],
        "first_event_at": iso8601 | None,
        "last_event_at": iso8601 | None,
        "description": str,
        "review_status": "PENDING",
    }
"""
from typing import Any, Dict, List

from .constants import (
    INCIDENT_BY_EVENT,
    INCIDENT_MIN_RUNS,
    INCIDENT_TYPE_LABELS,
)
from .events import EVENT_SOURCES


def _description(incident_type: str, runs: int, event_types: List[str]) -> str:
    label = INCIDENT_TYPE_LABELS.get(incident_type, incident_type.replace("_", " "))
    sources = sorted({EVENT_SOURCES.get(e, "ENGINE") for e in event_types})
    return (
        f"{label}: {runs} sustained event run(s) "
        f"({', '.join(sorted(set(event_types))) or 'n/a'}) from {', '.join(sources)}"
    )


class IncidentBuilder:
    """Turn a set of repeated-run event families into incident candidates.

    The ``repeated`` map is keyed by EVENT FAMILY (the stream the engine
    emits: ``OBJECT_PHONE``, ``FACE_MISSING``, ...). The configured minimum-run
    thresholds (``INCIDENT_MIN_RUNS``) are keyed by INCIDENT TYPE (the
    human-review surface: ``PHONE_USE``, ``FACE_ABSENT``, ...). ``build()``
    MUST resolve each family through ``INCIDENT_BY_EVENT`` before comparing
    against the threshold — looking the threshold up by family name directly
    always returned 0 and silently disabled every min-run rule.
    """

    def __init__(self, min_runs: Dict[str, int] = None):
        self._min = dict(min_runs or INCIDENT_MIN_RUNS)

    # ------------------------------------------------------------------
    def build(self, repeated: Dict[str, int], risk_label: str,
              first_ts=None, last_ts=None) -> List[Dict[str, Any]]:
        """``repeated`` = {event_family: distinct_run_count} from RepeatTracker.

        Only families whose incident TYPE reached its configured threshold
        produce a candidate. ``risk_label`` is the DETECTED state at detection
        time — stored for context, never used to auto-confirm anything.
        """
        candidates: List[Dict[str, Any]] = []
        for family, runs in sorted(repeated.items()):
            incident_type = INCIDENT_BY_EVENT.get(family, family)
            threshold = self._min.get(
                incident_type, self._min.get(family, 0)
            )
            if runs < threshold:
                continue
            event_types = [family]
            candidates.append({
                "incident_type": incident_type,
                "risk_level": risk_label,
                "confidence": round(min(1.0, 0.5 + 0.10 * (runs - threshold)), 4),
                "event_count": int(runs),
                "event_types": event_types,
                "first_event_at": first_ts,
                "last_event_at": last_ts,
                "description": _description(incident_type, runs, event_types),
                "review_status": "PENDING",
            })
        return candidates


incident_builder = IncidentBuilder()
