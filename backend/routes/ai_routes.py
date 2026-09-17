from fastapi import APIRouter, Depends

from ..ai_service.service import ai_service
from ..auth import require_admin
from ..schemas import AIHealthOut

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/health", response_model=AIHealthOut)
def ai_health(current_user=Depends(require_admin)):
    return ai_service.health()


@router.post("/verify")
def ai_verify(current_user=Depends(require_admin)):
    """Load/verify the models (YOLO fully; others staged)."""
    return ai_service.verify_models()