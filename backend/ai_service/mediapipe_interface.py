"""
MediaPipe face/landmark processing.

Stage 1: integration contract only. Full face landmark / presence /
multiple-person processing is implemented in Stage 3.
"""
from typing import Any, Dict

from .interfaces import FaceLandmarker


class MediaPipeFaceService(FaceLandmarker):
    name = "MEDIAPIPE"

    def __init__(self):
        self._loaded = False
        self._error = None

    def load(self) -> bool:
        # Stage 3: instantiate MediaPipe FaceMesh / FaceDetector solutions here.
        self._loaded = True
        return True

    def is_loaded(self) -> bool:
        return self._loaded

    def process(self, frame) -> Dict[str, Any]:
        raise NotImplementedError("MediaPipe processing pipeline arrives in Stage 3.")

    def health(self) -> Dict[str, Any]:
        return {
            "status": "available" if self.is_loaded() else "ready",
            "loaded": self.is_loaded(),
            "implemented": False,
            "note": "Integration contract only. Full MediaPipe pipeline in Stage 3.",
            "error": self._error,
        }


mediapipe_face_service = MediaPipeFaceService()