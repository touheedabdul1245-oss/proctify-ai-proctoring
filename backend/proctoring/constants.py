"""
Proctoring engine — shared constants and thresholds (Stage 3).

Everything signal/risk related is expressed here so the pure logic modules
(observation -> events -> temporal -> incidents -> risk) stay import-light and
testable without any neural-net dependency.
"""
from ..config import (
    GAZE_DEVIATION_THRESHOLD,
    HEAD_POSE_PITCH_THRESHOLD,
    HEAD_POSE_YAW_THRESHOLD,
    PROCTORING_CLIENT_POLL_INTERVAL_SECONDS,
    PROCTORING_SIMULATE_ALLOWED,
)

# --------------------------------------------------------------------------
# Event types emitted by the engine.
# --------------------------------------------------------------------------
EVENT_PHONE = "OBJECT_PHONE"
EVENT_EARPHONE = "OBJECT_EARPHONE"
EVENT_EXTRA_PERSON = "EXTRA_PERSON"
EVENT_FACE_MISSING = "FACE_MISSING"
EVENT_HEAD_DEVIATION = "HEAD_DEVIATION"
EVENT_GAZE_DEVIATION = "GAZE_DEVIATION"
EVENT_SPEECH = "SPEECH_DETECTED"
EVENT_CAMERA_UNAVAILABLE = "CAMERA_UNAVAILABLE"
EVENT_AUDIO_UNAVAILABLE = "AUDIO_UNAVAILABLE"

ALL_EVENT_TYPES = frozenset({
    EVENT_PHONE, EVENT_EARPHONE, EVENT_EXTRA_PERSON, EVENT_FACE_MISSING,
    EVENT_HEAD_DEVIATION, EVENT_GAZE_DEVIATION, EVENT_SPEECH,
    EVENT_CAMERA_UNAVAILABLE, EVENT_AUDIO_UNAVAILABLE,
})

# Sources that may produce each event (matches ai_service backends).
EVENT_SOURCES = {
    EVENT_PHONE: "YOLO",
    EVENT_EARPHONE: "YOLO",
    EVENT_EXTRA_PERSON: "MEDIAPIPE",
    EVENT_FACE_MISSING: "MEDIAPIPE",
    EVENT_HEAD_DEVIATION: "PNP",
    EVENT_GAZE_DEVIATION: "MEDIAPIPE",
    EVENT_SPEECH: "AUDIO",
    EVENT_CAMERA_UNAVAILABLE: "ENGINE",
    EVENT_AUDIO_UNAVAILABLE: "ENGINE",
}

# Severity used when persisting an ai_event row.
EVENT_SEVERITY = {
    EVENT_PHONE: "WARNING",
    EVENT_EARPHONE: "WARNING",
    EVENT_EXTRA_PERSON: "WARNING",
    EVENT_FACE_MISSING: "WATCH",
    EVENT_HEAD_DEVIATION: "WARNING",
    EVENT_GAZE_DEVIATION: "WATCH",
    EVENT_SPEECH: "WATCH",
    EVENT_CAMERA_UNAVAILABLE: "INFO",
    EVENT_AUDIO_UNAVAILABLE: "INFO",
}

# --------------------------------------------------------------------------
# Temporal / confirmation settings (per-event behaviour).
# --------------------------------------------------------------------------
# Minimum sustained presence before a single detection graduates into a
# confirmed event. Short clips are treated as noise, never as malpractice.
EVENT_MIN_SUSTAINED_SECONDS = {
    EVENT_PHONE: 2.0,
    EVENT_EARPHONE: 2.0,
    EVENT_EXTRA_PERSON: 2.0,
    EVENT_FACE_MISSING: 4.0,
    EVENT_HEAD_DEVIATION: 1.5,
    EVENT_GAZE_DEVIATION: 2.0,
    EVENT_SPEECH: 2.5,
    EVENT_CAMERA_UNAVAILABLE: 3.0,
    EVENT_AUDIO_UNAVAILABLE: 3.0,
}

# How long (seconds) a confirmed event stays "live" before the temporal window
# resets. Prevents a single glance registering as several separate events.
EVENT_COOLDOWN_SECONDS = {
    EVENT_PHONE: 20.0,
    EVENT_EARPHONE: 20.0,
    EVENT_EXTRA_PERSON: 20.0,
    EVENT_FACE_MISSING: 30.0,
    EVENT_HEAD_DEVIATION: 12.0,
    EVENT_GAZE_DEVIATION: 15.0,
    EVENT_SPEECH: 25.0,
    EVENT_CAMERA_UNAVAILABLE: 30.0,
    EVENT_AUDIO_UNAVAILABLE: 30.0,
}

# Minimum gap (seconds) of a *new* sustained run to count as a repeated event
# (used for repeated-detection analysis) rather than the same run re-arming.
EVENT_REPEAT_RESET_SECONDS = 30.0

# --------------------------------------------------------------------------
# Incident patterns.
# --------------------------------------------------------------------------
INCIDENT_PHONE = "PHONE_USE"
INCIDENT_EARPHONE = "EARPHONE_USE"
INCIDENT_EXTRA_PERSON = "EXTRA_PERSON"
INCIDENT_FACE_ABSENT = "FACE_ABSENT"
INCIDENT_MONITORING_BYPASS = "ENVIRONMENT_UNAVAILABLE"
INCIDENT_HEAD_DEVIATION = "HEAD_DEVIATION"
INCIDENT_GAZE_DEVIATION = "GAZE_DEVIATION"
INCIDENT_SPEECH = "SPEECH_ACTIVITY"

# Minimum number of DISTINCT sustained runs of the same event before the
# engine promotes the pattern into an incident candidate. Note: an incident
# is NEVER an auto-verdict — it is a candidate for human teacher review.
# INCIDENT_MIN_RUNS is keyed by INCIDENT_* (the human-review incident type),
# NOT by the event family. IncidentBuilder.build() receives event families and
# MUST resolve them through INCIDENT_BY_EVENT below; never look up a threshold
# by family name directly (that yielded 0 and silently disabled every
# threshold). See INCIDENT_BY_EVENT.
INCIDENT_MIN_RUNS = {
    INCIDENT_PHONE: 2,
    INCIDENT_EARPHONE: 2,
    INCIDENT_EXTRA_PERSON: 2,
    INCIDENT_FACE_ABSENT: 3,
    INCIDENT_MONITORING_BYPASS: 2,
    INCIDENT_HEAD_DEVIATION: 3,
    INCIDENT_GAZE_DEVIATION: 3,
    INCIDENT_SPEECH: 3,
}

# Single source of truth: event family -> incident type it can graduate into.
# The event stream is deliberately richer than the review surface — several
# families converge on ONE incident type (e.g. camera + audio unavailability
# both feed ENVIRONMENT_UNAVAILABLE). Threshold lookups and the persisted
# ``incident_type`` MUST go through this mapping.
INCIDENT_BY_EVENT = {
    EVENT_PHONE: INCIDENT_PHONE,
    EVENT_EARPHONE: INCIDENT_EARPHONE,
    EVENT_EXTRA_PERSON: INCIDENT_EXTRA_PERSON,
    EVENT_FACE_MISSING: INCIDENT_FACE_ABSENT,
    EVENT_CAMERA_UNAVAILABLE: INCIDENT_MONITORING_BYPASS,
    EVENT_AUDIO_UNAVAILABLE: INCIDENT_MONITORING_BYPASS,
    EVENT_HEAD_DEVIATION: INCIDENT_HEAD_DEVIATION,
    EVENT_GAZE_DEVIATION: INCIDENT_GAZE_DEVIATION,
    EVENT_SPEECH: INCIDENT_SPEECH,
}

# Per-family incident threshold (derived, so it can never drift from
# INCIDENT_MIN_RUNS + INCIDENT_BY_EVENT). Families absent from this map have no
# incident threshold and must never auto-promote.
INCIDENT_MIN_RUNS_BY_FAMILY = {
    family: INCIDENT_MIN_RUNS[typename]
    for family, typename in INCIDENT_BY_EVENT.items()
}

# --------------------------------------------------------------------------
# Risk bands (feature-vector approach, hysteresis-augmented).
#
# The risk engine builds a weighted *index* from active/sustained signals and
# maps it onto bands. It is NOT a "100 minus penalty" counter nor an
# auto-verdict mechanism. A single confirmed event only nudges the index; it
# never multiplies suspicion by itself.
# --------------------------------------------------------------------------
RISK_LEVELS = ("NORMAL", "ATTENTION", "ELEVATED", "HIGH")
RISK_BAND_UPPER = (0.30, 0.60, 1.20)  # upper bounds for NORMAL / ATTENTION / ELEVATED
RISK_HYSTERESIS = 0.08  # band margin that must be crossed to move back down

# Per-session-style feature weights (accumulated over a sliding window).
RISK_WEIGHT_EVENT = 0.05       # per single confirmed event
RISK_WEIGHT_INCIDENT = 0.45    # per confirmed incident pattern (human-reviewed candidate)
RISK_WEIGHT_SPEECH = 0.10
RISK_WEIGHT_UNAVAILABLE = 0.10
RISK_WEIGHT_TEMPORAL_FACES = 0.35  # sustained unknown-face/face-pressure
RISK_DECAY_HALF_LIFE = 60.0   # seconds; older signals decay so risk recedes naturally

RISK_LABEL_NORMAL = "NORMAL"
RISK_LABEL_ATTENTION = "ATTENTION"
RISK_LABEL_ELEVATED = "ELEVATED"
RISK_LABEL_HIGH = "HIGH"

# Thresholds reused by the engine when judging raw head pose / gaze.
HEAD_YAW_THRESHOLD = HEAD_POSE_YAW_THRESHOLD
HEAD_PITCH_THRESHOLD = HEAD_POSE_PITCH_THRESHOLD
GAZE_DEV_THRESHOLD = GAZE_DEVIATION_THRESHOLD

CLIENT_POLL_INTERVAL_SECONDS = PROCTORING_CLIENT_POLL_INTERVAL_SECONDS
SIMULATE_ALLOWED = PROCTORING_SIMULATE_ALLOWED

# --------------------------------------------------------------------------
# Derived aggregates — single source of truth, derived HERE from the scalars
# above so pure modules stay import-light and never drift. If a threshold
# changes, it changes in exactly ONE place.
# --------------------------------------------------------------------------
RISK_LABELS = tuple(RISK_LEVELS)  # band labels by level index (0..N)
RISK_LABEL_BY_LEVEL = {i: RISK_LEVELS[i] for i in range(len(RISK_LEVELS))}

RISK_WEIGHTS = {  # per-event-family contribution to the risk index
    EVENT_PHONE: RISK_WEIGHT_EVENT,
    EVENT_EARPHONE: RISK_WEIGHT_EVENT,
    EVENT_EXTRA_PERSON: RISK_WEIGHT_EVENT,
    EVENT_FACE_MISSING: RISK_WEIGHT_EVENT,
    EVENT_HEAD_DEVIATION: RISK_WEIGHT_EVENT,
    EVENT_GAZE_DEVIATION: RISK_WEIGHT_EVENT,
    EVENT_SPEECH: RISK_WEIGHT_EVENT,
    EVENT_CAMERA_UNAVAILABLE: RISK_WEIGHT_UNAVAILABLE,
    EVENT_AUDIO_UNAVAILABLE: RISK_WEIGHT_UNAVAILABLE,
}

INCIDENT_TYPE_LABELS = {
    INCIDENT_PHONE: "Phone use",
    INCIDENT_EARPHONE: "Earphone use",
    INCIDENT_EXTRA_PERSON: "Extra person present",
    INCIDENT_FACE_ABSENT: "Face persistently absent",
    INCIDENT_MONITORING_BYPASS: "Environment unavailability",
    INCIDENT_HEAD_DEVIATION: "Head deviation",
    INCIDENT_GAZE_DEVIATION: "Gaze deviation",
    INCIDENT_SPEECH: "Speech/audio activity",
}

# Per-family cooldown (temporal.CooldownGate). Copy of the per-event cooldown
# scalars so both inter-module contracts agree on the SAME seconds table.
COOLDOWN_BY_FAMILY = dict(EVENT_COOLDOWN_SECONDS)
COOLDOWN_BY_FAMILY.setdefault("*", 15.0)

# --------------------------------------------------------------------------
# Stage 6 — Numeric Trust Score (0..100).
#
# TRUST is a 0..100 score derived from THE SAME confirmed, cooldown-synced
# event stream that drives the risk bands — it is NOT a second risk model.
# The full formula (implemented in engine.py and mirrored here as config):
#
#     start                         100 per session (clamped 0..100)
#     penalty per confirmed event   TRUST_PENALTY_BASE
#                                   * TRUST_EVENT_WEIGHTS[family]
#                                   * confidence (floor TRUST_CONFIDENCE_FLOOR)
#                                   * min(1, sustained / TRUST_SUSTAINED_REF_SECONDS)
#                                   * (1 + TRUST_REPEAT_ESCALATION_PER_STEP
#                                          * min(runs-1, TRUST_REPEAT_MAX_STEPS))
#     per-ingest cap                TRUST_MAX_PENALTY_PER_INGEST
#     recovery                      exponential approach toward the CURRENT
#                                   trust band's ceiling (see TRUST_SCORE_RANGES),
#                                   applied only after at least
#                                   TRUST_RECOVERY_CLEAN_SECONDS with NO
#                                   confirmed events:
#                                       += (ceiling - trust) * dt / TRUST_RECOVERY_CONSTANT_SECONDS
#
# TRUST SCORE RANGES (0..100, the single source of truth for the student pill):
#
#     NORMAL      80 .. 100
#     ATTENTION   60 .. 79
#     ELEVATED    40 .. 59
#     HIGH         0 .. 39
#
# RULES enforced in engine.py:
#   * AI raw detections or PENDING incident candidates NEVER move trust; only
#     *confirmed* (sustained + cooldown-synced) events do. No AI auto-verdict.
#   * Per-family cooldown already dedupes the same underlying observation, so
#     a single behaviour is never double-penalized.
#   * Incidents (teacher-confirmed/dismissed) stay separate from the raw
#     score; creating an incident adds NO second penalty.
#   * Recovery is gated by TRUST_SCORE_RANGES: the ceiling is the current
#     band's upper bound (100 / 79 / 59) and is frozen at 0 while the band is
#     HIGH (score < 40). There is no arbitrary restore.
# --------------------------------------------------------------------------
TRUST_BASE_SCORE = 100.0
TRUST_FLOOR = 0.0
TRUST_CEILING = 100.0

TRUST_PENALTY_BASE = 4.0
TRUST_EVENT_WEIGHTS = {
    EVENT_PHONE: 1.0,
    EVENT_EARPHONE: 1.0,
    EVENT_EXTRA_PERSON: 1.2,
    EVENT_FACE_MISSING: 0.5,
    EVENT_HEAD_DEVIATION: 0.6,
    EVENT_GAZE_DEVIATION: 0.5,
    EVENT_SPEECH: 0.5,
    EVENT_CAMERA_UNAVAILABLE: 0.3,
    EVENT_AUDIO_UNAVAILABLE: 0.3,
}
TRUST_EVENT_WEIGHT_DEFAULT = 0.8
TRUST_CONFIDENCE_FLOOR = 0.3
TRUST_SUSTAINED_REF_SECONDS = 8.0
TRUST_REPEAT_ESCALATION_PER_STEP = 0.4
TRUST_REPEAT_MAX_STEPS = 5
TRUST_MAX_PENALTY_PER_INGEST = 20.0
TRUST_RECOVERY_CLEAN_SECONDS = 60.0
TRUST_RECOVERY_CONSTANT_SECONDS = 90.0

TRUST_LEVEL_NORMAL = RISK_LABELS[0]
TRUST_LEVEL_ATTENTION = RISK_LABELS[1]
TRUST_LEVEL_ELEVATED = RISK_LABELS[2]
TRUST_LEVEL_HIGH = RISK_LABELS[3]

# Trust score ranges (single source of truth for trust_level_for / client pill).
TRUST_SCORE_RANGES = {
    TRUST_LEVEL_NORMAL: (80.0, 100.0),
    TRUST_LEVEL_ATTENTION: (60.0, 79.999),
    TRUST_LEVEL_ELEVATED: (40.0, 59.999),
    TRUST_LEVEL_HIGH: (0.0, 39.999),
}

# Current-band recovery ceiling per TRUST level (synchronized with
# TRUST_SCORE_RANGES / TRUST_SCORE_BANDS above). The score can never recover
# beyond its current band, and HIGH is frozen at the floor.
TRUST_BAND_CEILING = {
    TRUST_LEVEL_NORMAL: 100.0,   # score in 80..100
    TRUST_LEVEL_ATTENTION: 79.0,  # score in 60..79
    TRUST_LEVEL_ELEVATED: 59.0,   # score in 40..59
    TRUST_LEVEL_HIGH: 0.0,        # score in 0..39 -> frozen at floor
}


def trust_level_for(score: float) -> str:
    """Map a numeric trust score (0..100) onto its band label.

    Bands (single source of truth — mirrors TRUST_SCORE_RANGES):
        NORMAL      80..100
        ATTENTION   60..79
        ELEVATED    40..59
        HIGH         0..39
    """
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = TRUST_BASE_SCORE
    if value >= TRUST_SCORE_RANGES[TRUST_LEVEL_NORMAL][0]:
        return TRUST_LEVEL_NORMAL
    if value >= TRUST_SCORE_RANGES[TRUST_LEVEL_ATTENTION][0]:
        return TRUST_LEVEL_ATTENTION
    if value >= TRUST_SCORE_RANGES[TRUST_LEVEL_ELEVATED][0]:
        return TRUST_LEVEL_ELEVATED
    return TRUST_LEVEL_HIGH
