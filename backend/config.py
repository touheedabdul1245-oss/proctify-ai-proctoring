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