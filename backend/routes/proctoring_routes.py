"""
Stage-3 proctoring API surface.

Request-driven ingest: the client posts ONE decoded observation (or a base64
frame data-URL) plus camera/audio availability flags, and receives back a
compact, deterministic signal: extracted events, banded risk snapshot and any
incident candidates that the builder graduated to *human review* (always
PENDING — the engine never auto-verdicts).

Conventions match the rest of the repo:
  * teachers/admins only for ingest + bands (proctoring is an exam-integrity
    surface, not a student-facing one);
  * the engine is session-scoped and lives in-memory per exam session;
    persistence to SQL (`ai_events`/`incidents`/`risk_scores`/`evidence`) is
    the caller's job and deliberately NOT performed here (pure engine).
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_admin, require_teacher
from ..proctoring import (
    INGEST_SIMULATE_ALLOWED,
    bands_contract,
    build_engine,
    simulate_allowed,
    stream_from_observation,
)
from ..schemas import (
    ProctoringBandsOut,
    ProctoringIngestIn,
    ProctoringSignalOut,
)

router = APIRouter(prefix="/api/proctoring", tags=["proctoring"])


@router.get("/bands", response_model=ProctoringBandsOut)
def proctoring_bands(current_user: Any = Depends(require_teacher)):
    """Risk band contract: levels, hysteresis, per-family weights. This is the
    read-only config surface the student pill + teacher review UIs depend on."""
    bands = bands_contract()
    return ProctoringBandsOut(
        bands=bands,
        simulate_allowed=bool(simulate_allowed()),
    )


@router.post("/ingest", response_model=ProctoringSignalOut)
def proctoring_ingest(payload: ProctoringIngestIn,
                      current_user: Any = Depends(require_teacher)):
    """Run one frame's observation through the session engine and return the
    signal snapshot: extracted events, banded risk AND incident candidates
    (all PENDING human review)."""
    try:
        session_id = int(payload.session_token)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid session token")

    if payload.observation:
        observation: Dict[str, Any] = payload.observation
    else:
        # frame data-URL path: still handled upstream by the AI/ingest layer
        # (decoding + evidence capture); here we only accept observations so
        # the engine surface stays pure and deterministic.
        raise HTTPException(
            status_code=422,
            detail="Proctoring ingest requires an 'observation' payload",
        )

    engine = build_engine(exam_session_id=session_id)
    signal = stream_from_observation(engine, observation)
    return ProctoringSignalOut(
        risk=signal.get("risk", {}),
        runs=signal.get("runs"),
        repeated=signal.get("repeated"),
        incident_candidates=signal.get("incident_candidates"),
    )
