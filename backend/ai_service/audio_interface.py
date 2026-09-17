"""
Audio / speech analysis.

Stage 1: integration contract only. Voice activity / speech detection
(and optionally speaker verification) arrives in Stage 3.
"""
from typing import Any, Dict

from .interfaces import AudioAnalyzer


class AudioService(AudioAnalyzer):
    name = "AUDIO"

    def __init__(self):
        self._loaded = False
        self._error = None

    def load(self) -> bool:
        # Stage 3: load a pretrained audio/speech model or detector here.
        self._loaded = True
        return True

    def is_loaded(self) -> bool:
        return self._loaded

    def analyze(self, audio_chunk) -> Dict[str, Any]:
        raise NotImplementedError("Audio analysis arrives in Stage 3.")

    def health(self) -> Dict[str, Any]:
        return {
            "status": "available" if self.is_loaded() else "ready",
            "loaded": self.is_loaded(),
            "implemented": False,
            "note": "Integration contract only. Audio pipeline in Stage 3.",
            "error": self._error,
        }


audio_service = AudioService()