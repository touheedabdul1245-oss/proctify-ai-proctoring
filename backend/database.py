from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import DATABASE_URL

engine_kwargs = {"echo": False}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  ensure models are registered

    _migrate_stage2(engine)
    Base.metadata.create_all(bind=engine)


def _migrate_stage2(engine):
    """Upgrade the reserved Stage-1 exam_sessions/answers tables to the Stage-2
    schema if the app previously created them with the old column set.

    Both tables are empty in every known environment, so the safe upgrade path
    is to drop and let ``create_all`` rebuild them with the current schema.
    If rows ever exist, ALTER TABLE is used to preserve the data instead.
    """
    if not engine.dialect.name == "sqlite":
        return
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {r[0] for r in cur.fetchall()}

        def columns(table):
            cur.execute(f"PRAGMA table_info({table})")
            return {r[1] for r in cur.fetchall()}

        def add_column(table, column, definition):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        if "answers" in existing:
            cols = columns("answers")
            if "marked_for_review" not in cols or "saved_at" not in cols:
                cur.execute("SELECT COUNT(*) FROM answers")
                if cur.fetchone()[0] == 0:
                    cur.execute("DROP TABLE answers")
                    existing.discard("answers")
                else:
                    if "marked_for_review" not in cols:
                        add_column("answers", "marked_for_review", "BOOLEAN DEFAULT 0 NOT NULL")
                    if "saved_at" not in cols:
                        add_column("answers", "saved_at", "DATETIME")

        if "exam_sessions" in existing:
            cols = columns("exam_sessions")
            if "last_activity_at" not in cols or "expired_at" not in cols:
                cur.execute("SELECT COUNT(*) FROM exam_sessions")
                if cur.fetchone()[0] == 0:
                    cur.execute("DROP TABLE exam_sessions")
                    existing.discard("exam_sessions")
                else:
                    if "last_activity_at" not in cols:
                        add_column("exam_sessions", "last_activity_at", "DATETIME")
                    if "submitted_at" not in cols:
                        add_column("exam_sessions", "submitted_at", "DATETIME")
                    if "expired_at" not in cols:
                        add_column("exam_sessions", "expired_at", "DATETIME")

        raw.commit()
    finally:
        raw.close()


def utcnow():
    return datetime.utcnow()