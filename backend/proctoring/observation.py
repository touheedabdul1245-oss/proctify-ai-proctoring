"""
Observation ingestion (Stage 3).

Turns one decoded frame + camera/audio availability flags into a NORMALISED,
resolution-independent ``Observation``. This module is PURE — it only decodes
and shapes input; it never decides anything about a student.

The engine consumes observations exclusively through this container so every
downstream heuristic (events / temporal / incidents / risk) works on a stable
contract regardless of the camera format or AI backend available.
"""
import base64
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np

_LIMIT_PIXELS = 640 * 480


class Observation:
    """Normalized frame observation (pure container)."""

    __slots__ = ("image", "camera_available", "camera_error", "width", "height")

    def __init__(self, image: Optional[np.ndarray],
                 camera_available: bool = True,
                 camera_error: Optional[str] = None):
        self.image = image
        self.camera_available = bool(camera_available)
        self.camera_error = camera_error
        if image is not None and getattr(image, "ndim", 0) >= 2:
            self.height = int(image.shape[0])
            self.width = int(image.shape[1])
        else:
            self.height = 0
            self.width = 0

    @property
    def has_image(self) -> bool:
        return self.image is not None and self.camera_available

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_image": self.has_image,
            "width": self.width,
            "height": self.height,
            "camera_available": self.camera_available,
            "camera_error": self.camera_error,
        }


def from_frame(frame: Any, camera_available: bool = True,
               camera_error: Optional[str] = None) -> Observation:
    """Build an Observation from a raw (cv2 BGR or RGB or gray) frame."""
    if frame is None or not camera_available:
        return Observation(None, camera_available=camera_available,
                           camera_error=camera_error or "no frame")

    arr = np.asarray(frame)
    if arr.ndim == 2:  # gray -> RGB
        arr = np.repeat(arr[:, :, None], 3, axis=2)
    elif arr.ndim == 3 and arr.shape[2] == 4:  # RGBA -> RGB
        arr = arr[:, :, :3]
    arr = arr.astype(np.uint8)
    if arr.shape[0] * arr.shape[1] > _LIMIT_PIXELS:
        return Observation(None, camera_available=False,
                           camera_error="frame too large")
    return Observation(arr, camera_available=True, camera_error=None)


def decode_data_url(data_url: Optional[str]) -> Optional[np.ndarray]:
    """Decode a ``data:image/*;base64,....`` payload into an RGB ndarray."""
    if not data_url:
        return None
    m = re.match(r"data:image/[a-zA-Z0-9+.-]+;base64,(.+)", data_url, re.S)
    if not m:
        return None
    try:
        raw = base64.b64decode(m.group(1))
    except Exception:
        return None
    if not raw:
        return None
    try:
        import cv2
        buf = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)  # BGR
        if img is None:
            return None
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    except Exception:
        return None
