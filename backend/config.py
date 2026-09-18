import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# YOLO model lives in the PROCTIFY_V2 project (existing custom-trained model).
# We only reference it and load it read-only. We never retrain/modify it.
YOLO_WEIGHTS_DIR = Path(
    os.environ.get(
        "PROCTIFY_YOLO_WEIGHTS_DIR",
        r"C:\Users\touhe\PROCTIFY_V2\runs\detect\proctify_phone_earphone_v2\weights",
    )
)

YOLO_MODEL_NAME = os.environ.get("PROCTIFY_YOLO_MODEL_NAME", "best.pt")

YOLO_MODEL_PATH = YOLO_WEIGHTS_DIR / YOLO_MODEL_NAME

# SQLite primary database (SQL is the source of truth).
SQLITE_PATH = BASE_DIR / "datastore" / "proctify.db"

# Prefer explicit DATABASE_URL; otherwise default to bundled SQLite.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{SQLITE_PATH.as_posix()}"
)

JWT_SECRET = os.environ.get(
    "PROCTIFY_JWT_SECRET", "proctify-dev-secret-change-in-production"
)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("PROCTIFY_TOKEN_EXPIRE_MINUTES", 720))

# Security: initial bootstrapped admin credentials (only used once on empty DB).
BOOTSTRAP_ADMIN_EMAIL = os.environ.get("PROCTIFY_ADMIN_EMAIL", "admin@proctify.dev")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("PROCTIFY_ADMIN_PASSWORD", "Admin@123")

DEFAULT_STUDENT_PASSWORD = os.environ.get("PROCTIFY_STUDENT_PASSWORD", "Student@123")

# Bulk enrollment limits.
MAX_BULK_ROWS = int(os.environ.get("PROCTIFY_MAX_BULK_ROWS", 2000))

# Exam state machine.
EXAM_STATES = ["DRAFT", "SCHEDULED", "AVAILABLE", "ACTIVE", "COMPLETED", "ARCHIVED"]
EXAM_TRANSITIONS = {
    "DRAFT": ["SCHEDULED", "ARCHIVED"],
    "SCHEDULED": ["AVAILABLE", "DRAFT", "COMPLETED", "ARCHIVED"],
    "AVAILABLE": ["ACTIVE", "COMPLETED", "ARCHIVED", "SCHEDULED"],
    "ACTIVE": ["COMPLETED", "ARCHIVED"],
    "COMPLETED": ["ARCHIVED"],
    "ARCHIVED": [],
}

USER_ROLES = ["student", "teacher", "admin"]

# Stage 2: pre-exam identity still-capture storage (metadata lives in SQL).
SESSION_PHOTO_DIR = BASE_DIR / "datastore" / "session_photos"

# ---------------------------------------------------------------------------
# Stage 3 — AI proctoring engine configuration.
# All AI assets are EXISTING components referenced read-only. Nothing here is
# trained, downloaded or replaced.
# ---------------------------------------------------------------------------

# MediaPipe face landmarking.
# Prefer the existing MediaPipe Task asset from PROCTIFY_V2 when present;
# otherwise fall back to the bundled solutions.face_mesh model.
FACE_LANDMARKER_MODEL_PATH = Path(
    os.environ.get(
        "PROCTIFY_FACE_LANDMARKER_MODEL_PATH",
        r"C:\Users\touhe\PROCTIFY_V2\models\face_landmarker\face_landmarker.task",
    )
)
MEDIAPIPE_MAX_FACES = int(os.environ.get("PROCTIFY_MEDIAPIPE_MAX_FACES", 20))
MEDIAPIPE_MIN_DETECTION_CONFIDENCE = float(
    os.environ.get("PROCTIFY_MEDIAPIPE_MIN_DETECTION_CONFIDENCE", 0.5)
)

# Head-pose (PnP) — thresholds in degrees for "deviation from frontal".
HEAD_POSE_YAW_THRESHOLD = float(os.environ.get("PROCTIFY_HEAD_POSE_YAW_THRESHOLD", 28.0))
HEAD_POSE_PITCH_THRESHOLD = float(os.environ.get("PROCTIFY_HEAD_POSE_PITCH_THRESHOLD", 26.0))

# Gaze deviation — normalized eye-offset beyond which gaze is considered off-screen.
GAZE_DEVIATION_THRESHOLD = float(os.environ.get("PROCTIFY_GAZE_DEVIATION_THRESHOLD", 0.32))

# Audio voice-activity detection.
AUDIO_SPEECH_RMS_THRESHOLD = float(os.environ.get("PROCTIFY_AUDIO_SPEECH_RMS_THRESHOLD", 0.012))
AUDIO_ANALYSIS_WINDOW_SECONDS = float(os.environ.get("PROCTIFY_AUDIO_ANALYSIS_WINDOW_SECONDS", 2.0))

# Proctoring engine.
PROCTORING_ENABLED = os.environ.get("PROCTIFY_PROCTORING_ENABLED", "1") != "0"
# When 1, the observation API honors an explicit "detections" override payload.
# Used ONLY by deterministic tests/CI. Disabled in production.
PROCTORING_SIMULATE_ALLOWED = os.environ.get("PROCTIFY_PROCTORING_SIMULATE_ALLOWED", "0") == "1"
# Client-visible status cadence hint (the student app polls at ~this interval).
PROCTORING_CLIENT_POLL_INTERVAL_SECONDS = int(
    os.environ.get("PROCTIFY_PROCTORING_CLIENT_POLL_INTERVAL_SECONDS", 5)
)

# Evidence snapshot storage (metadata lives in SQL).
EVIDENCE_DIR = BASE_DIR / "datastore" / "evidence"