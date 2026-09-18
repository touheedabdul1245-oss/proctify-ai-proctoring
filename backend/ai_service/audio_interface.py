"""
Audio / speech analysis (Stage 3).

Classifies a PCM audio chunk for speech / voice activity entirely with local
signal processing (RMS energy, zero-crossing rate, spectral voice-band ratio).
No external model is downloaded or trained. Uses the EXISTING audio assets
only (the microphone), matching the "integrate existing components" boundary.

    analyze(audio_chunk, sample_rate=16000) -> {
        "available": True,
        "rms": float, "zcr": float, "voice_band_ratio": float,
        "speech_probability": 0..1, "speech_detected": bool,
        "silence": bool, "duration_seconds": float,
    }
"""
import math
import threading
from typing import Any, Dict, Optional, Sequence

from ..config import AUDIO_SPEECH_RMS_THRESHOLD
from .interfaces import AudioAnalyzer

_VOICE_BAND_LOW = 300.0
_VOICE_BAND_HIGH = 3400.0


def _to_float(samples: Sequence[Any]) -> Sequence[float]:
    """Normalize either integer PCM (int16/etc.) or float samples to -1..1."""
    if not len(samples):
        return []
    import numpy as np
    arr = np.asarray(samples)
    if arr.dtype.kind == "f":
        return arr.astype(np.float64)
    if arr.dtype.kind in "iu":
        info = np.iinfo(arr.dtype)
        if info.max == 0:
            return np.zeros_like(arr, dtype=np.float64)
        return (arr.astype(np.float64) - info.min) * (2.0 / (info.max - info.min)) - 1.0
    return arr.astype(np.float64)


def analyze_pcm(samples: Sequence[Any], sample_rate: int = 16000,
                window_seconds: float = 0.03) -> Dict[str, Any]:
    """Pure signal-processing speech/VAD analysis. No I/O — safe for tests."""
    import numpy as np

    data = _to_float(samples)
    if len(data) < 2:
        return {
            "available": True, "rms": 0.0, "zcr": 0.0, "voice_band_ratio": 0.0,
            "speech_probability": 0.0, "speech_detected": False, "silence": True,
            "duration_seconds": 0.0, "samples": int(len(data)),
        }

    f = np.asarray(data, dtype=np.float64)
    n = f.shape[0]

    rms = float(np.sqrt(np.mean(f ** 2)))
    if rms <= 1e-9:
        zcr = 0.0
    else:
        zcr = float(np.mean(np.abs(np.diff(np.sign(f))) > 0.5))

    # Frame-wise spectral voice-band ratio.
    win = int(sample_rate * window_seconds)
    if win < 8:
        win = 8
    step = max(win // 2, 1)
    band_ratios = []
    for start in range(0, n - win + 1, step):
        frame = f[start:start + win] * np.hanning(win)
        spec = np.abs(np.fft.rfft(frame)) ** 2
        total = float(spec.sum())
        if total <= 1e-12:
            continue
        freqs = np.fft.rfftfreq(win, d=1.0 / sample_rate)
        mask = (freqs >= _VOICE_BAND_LOW) & (freqs <= _VOICE_BAND_HIGH)
        band_ratios.append(float(spec[mask].sum()) / total)
    voice_ratio = float(np.mean(band_ratios)) if band_ratios else 0.0

    duration = n / float(sample_rate)
    # Heuristic probability bridge: energy gate + speech-band content + ZCR in
    # the typical speech range. Only a SIGNAL, never a verdict.
    energy_contrib = min(1.0, rms / max(AUDIO_SPEECH_RMS_THRESHOLD, 1e-6))
    band_contrib = min(1.0, max(0.0, (voice_ratio - 0.25) / 0.35)) if duration >= 0.1 else 0.0
    zcr_contrib = min(1.0, zcr * 4.0)
    probability = max(0.0, min(1.0, 0.45 * energy_contrib + 0.35 * band_contrib + 0.20 * zcr_contrib))
    speech = probability >= 0.55 and rms >= AUDIO_SPEECH_RMS_THRESHOLD

    return {
        "available": True,
        "rms": round(rms, 6),
        "zcr": round(zcr, 4),
        "voice_band_ratio": round(voice_ratio, 4),
        "speech_probability": round(probability, 4),
        "speech_detected": bool(speech),
        "silence": rms < 0.005,
        "duration_seconds": round(duration, 4),
        "samples": int(n),
    }


class AudioService(AudioAnalyzer):
    name = "AUDIO"

    def __init__(self):
        self._loaded = False
        self._error = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def load(self) -> bool:
        with self._lock:
            if self._loaded:
                return True
            try:
                import numpy  # noqa: F401
                self._loaded = True
                self._error = None
                return True
            except Exception as exc:
                self._loaded = False
                self._error = f"{type(exc).__name__}: {exc}"
                return False

    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    def analyze(self, audio_chunk, sample_rate: int = 16000) -> Dict[str, Any]:
        if not self.is_loaded():
            self.load()
        if not self.is_loaded():
            return {"available": False, "error": self._error}
        try:
            return analyze_pcm(audio_chunk, sample_rate=sample_rate)
        except Exception as exc:
            return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        loaded = self.is_loaded() or self.load()
        return {
            "status": "ok" if loaded else "unavailable",
            "loaded": loaded,
            "implemented": True,
            "error": self._error,
        }


audio_service = AudioService()