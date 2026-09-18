import csv
import io
import logging
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD
from .database import SessionLocal, init_db
from .models import Student, Teacher, User
from .auth import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("proctify")

app = FastAPI(
    title="PROCTIFY — AI-Assisted Online Examination System",
    description="Stage 1: Core platform (users, enrollment, exams). "
                "AI Service Layer wired for YOLO health check.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def bootstrap():
    """Create tables and seed a default admin (only if DB is empty)."""
    init_db()
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                email=BOOTSTRAP_ADMIN_EMAIL,
                password_hash=hash_password(BOOTSTRAP_ADMIN_PASSWORD),
                full_name="System Administrator",
                role="admin",
            )
            db.add(admin)
            db.commit()
            logger.info("Seeded default admin: %s", BOOTSTRAP_ADMIN_EMAIL)
    finally:
        db.close()


bootstrap()

from .routes.auth_routes import router as auth_router          # noqa: E402
from .routes.user_routes import router as user_router          # noqa: E402
from .routes.class_routes import router as class_router        # noqa: E402
from .routes.exam_routes import router as exam_router          # noqa: E402
from .routes.student_routes import router as student_router    # noqa: E402
from .routes.session_routes import router as session_router    # noqa: E402
from .routes.ai_routes import router as ai_router              # noqa: E402

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(class_router)
app.include_router(exam_router)
app.include_router(student_router)
app.include_router(session_router)
app.include_router(ai_router)


@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "proctify-backend", "stage": 1, "time": datetime.utcnow().isoformat()}