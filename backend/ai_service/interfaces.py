"""
AI Service Layer interfaces.

The application talks to this layer only. Concrete implementations for
YOLO / MediaPipe / PnP / Audio live behind these interfaces so examination
business logic is never coupled to a specific AI framework.

Stage 1: YOLO is implemented (load/verify/health of the existing model).
MediaPipe, PnP and Audio are integration contracts (implemented in Stage 3).
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AIBackend(ABC):
    """Common contract for every AI service backend."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return operational status of the backend."""


class ObjectDetector(AIBackend):
    """Contract for object detection (custom-trained YOLO phone/earphone model)."""
    name = "YOLO"

    @abstractmethod
    def load(self) -> bool:
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        ...

    @abstractmethod
    def detect(self, frame) -> List[Dict[str, Any]]:
        """Detect object instances in a frame.

        Returns list of {class_name, confidence, bbox:[x1,y1,x2,y2]}.
        Not invoked in Stage 1 outside health verification.
        """


class FaceLandmarker(AIBackend):
    """Contract for MediaPipe face/landmark processing. Stage 3."""
    name = "MEDIAPIPE"

    @abstractmethod
    def load(self) -> bool:
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        ...

    @abstractmethod
    def process(self, frame) -> Dict[str, Any]:
        ...


class HeadPoseEstimator(AIBackend):
    """Contract for PnP-based head-pose estimation. Stage 3."""
    name = "PNP"

    @abstractmethod
    def load(self) -> bool:
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        ...

    @abstractmethod
    def estimate(self, landmarks) -> Dict[str, Any]:
        ...


class AudioAnalyzer(AIBackend):
    """Contract for audio/speech analysis. Stage 3."""
    name = "AUDIO"

    @abstractmethod
    def load(self) -> bool:
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        ...

    @abstractmethod
    def analyze(self, audio_chunk) -> Dict[str, Any]:
        ...