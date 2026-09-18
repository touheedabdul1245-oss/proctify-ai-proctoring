"""Stage 5 — evidence media serving.

Serves captured snapshot files from the evidence datastore to CCTV-level
review surfaces. Teacher/admin only. Path traversal is blocked by realpath
normalization: the resolved path must stay inside EVIDENCE_DIR, and the
combined `file_path` (``<session_token>/<filename>``) must match a persisted
Evidence row exactly.
"""
import base64
import os

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_teacher
from ..config import EVIDENCE_DIR
from ..database import get_db
from ..models import Evidence, User

router = APIRouter(prefix="/api/evidence", tags=["evidence-media"])

_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def evidence_src(e: Evidence) -> str:
    """API-addressable path for a persisted evidence row (frontend uses as-is)."""
    return f"/api/evidence/{e.file_path}" if e.file_path else ""


@router.get("/{rel_path:path}")
def serve_evidence(
    rel_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    rel_path = rel_path.strip("/")
    if not rel_path or ".." in rel_path or "\\" in rel_path:
        raise HTTPException(status_code=400, detail="Invalid evidence path")
    row = db.query(Evidence).filter(Evidence.file_path == rel_path).first()
    if not row:
        raise HTTPException(status_code=404, detail="Evidence not found")

    root = EVIDENCE_DIR.resolve()
    target = (EVIDENCE_DIR / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid evidence path")

    if not target.is_file():
        raise HTTPException(status_code=404, detail="Evidence file missing")

    mime = _EXT_TO_MIME.get(target.suffix.lower(), "application/octet-stream")
    body = target.read_bytes()
    etag = base64.urlsafe_b64encode(os.fsencode(rel_path)).decode()[:20]
    return Response(
        content=body,
        media_type=mime,
        headers={
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{etag}"',
        },
    )