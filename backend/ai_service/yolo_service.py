"""
YOLO object detector for PROCTIFY.

Loads the existing custom-trained model (best.pt) from PROCTIFY_V2 and exposes
a health/status check. It NEVER downloads, retrains, or modifies the model —
we operate on it read-only.

Detection output contract: list of
    {"class_name": str, "class_id": int, "confidence": float, "bbox": [x1, y1, x2, y2]}
"""
import os
import threading
from typing import Any, Dict, List, Optional

from ..config import YOLO_MODEL_PATH, YOLO_WEIGHTS_DIR
from .interfaces import ObjectDetector


class YOLOService(ObjectDetector):
    name = "YOLO"

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()
        self._error: Optional[str] = None
        self._class_names: List[str] = []
        self._load_attempted = False
        self._loaded = False
        self._model_path = YOLO_MODEL_PATH
        self._model_path_str = str(YOLO_MODEL_PATH)

    @property
    def model_path(self) -> str:
        return self._model_path_str

    def _available(self) -> bool:
        return os.path.isfile(self._model_path_str)

    # ------------------------------------------------------------------
    # Load / verify
    # ------------------------------------------------------------------
    def load(self) -> bool:
        with self._lock:
            if self._loaded:
                return True
            if self._load_attempted and not self._model:
                return False
            self._load_attempted = True
            try:
                from ultralytics import YOLO
                self._model = YOLO(self._model_path_str)
                # Trigger a real forward pass on a dummy frame to verify the
                # weights actually load and run end-to-end.
                import numpy as np
                dummy = np.zeros((480, 640, 3), dtype=np.uint8)
                self._model.predict(dummy, verbose=False, conf=0.5)
                self._loaded = True
                self._error = None
                names = getattr(self._model, "names", None)
                if names:
                    self._class_names = list(names.values())
                return True
            except Exception as exc:
                self._loaded = False
                self._error = f"{type(exc).__name__}: {exc}"
                self._model = None
                return False

    def is_loaded(self) -> bool:
        return self._loaded

    def reload(self) -> bool:
        with self._lock:
            self._model = None
            self._loaded = False
            self._load_attempted = False
        return self.load()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        path_exists = self._available()
        loaded = self.is_loaded()

        if not loaded and path_exists:
            loaded = self.load()

        return {
            "status": "ok" if loaded else ("unavailable" if not path_exists else "error"),
            "model": os.path.basename(self._model_path_str) if self._model_path_str else None,
            "path": self._model_path_str,
            "path_exists": path_exists,
            "loaded": loaded,
            "class_names": self._class_names,
            "error": self._error,
        }

    # ------------------------------------------------------------------
    # Detection (full pipeline wired in Stage 3)
    # ------------------------------------------------------------------
    def detect(self, frame) -> List[Dict[str, Any]]:
        if not self.is_loaded():
            if not self.load():
                raise RuntimeError(f"YOLO model not available: {self._error}")
        results = self._model.predict(frame, verbose=False, conf=0.4)
        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                detections.append({
                    "class_id": cls_id,
                    "class_name": self._class_names[cls_id] if cls_id < len(self._class_names) else str(cls_id),
                    "confidence": round(conf, 4),
                    "bbox": [x1, y1, x2, y2],
                })
        return detections


yolo_service = YOLOService()