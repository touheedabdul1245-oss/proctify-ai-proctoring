"""
AI Service Layer entrypoint.

Application code depends on this facade only. The layer owns model lifecycle
(load / verify / health) and will orchestrate the realtime monitoring pipeline
in Stage 3 (YOLO + MediaPipe + PnP + Audio).
"""
from typing import Any, Dict

from .yolo_service import yolo_service
from .mediapipe_interface import mediapipe_face_service
from .pnp_interface import pnp_head_pose_service
from .audio_interface import audio_service


class AIService:
    def __init__(self):
        self.yolo = yolo_service
        self.mediapipe = mediapipe_face_service
        self.pnp = pnp_head_pose_service
        self.audio = audio_service

    def health(self) -> Dict[str, Any]:
        return {
            "yolo": self.yolo.health(),
            "mediapipe": self.mediapipe.health(),
            "pnp": self.pnp.health(),
            "audio": self.audio.health(),
        }

    def verify_models(self) -> Dict[str, Any]:
        """Load/verify every available model. YOLO is fully verified in Stage 1."""
        yolo = self.yolo.load()
        self.mediapipe.load()
        self.pnp.load()
        self.audio.load()
        return {
            "yolo_loaded": yolo,
            "mediapipe_ready": self.mediapipe.is_loaded(),
            "pnp_ready": self.pnp.is_loaded(),
            "audio_ready": self.audio.is_loaded(),
        }


ai_service = AIService()