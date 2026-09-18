"""
PnP-based head-pose estimation (Stage 3).

Solves the perspective-n-point problem with ``cv2.solvePnP`` using the
standard 3D reference face model mapped onto the 2D landmarks produced by the
MediaPipe face service. Returns yaw/pitch/roll in degrees routed through the
proctoring engine thresholds (config HEAD_POSE_*).

    estimate(landmarks) -> {
        "available": True,
        "yaw": deg, "pitch": deg, "roll": deg,
        "points": <n_used>, "reprojection": <px error> or None,
    }
"""
import math
import threading
from typing import Any, Dict, Optional

from .interfaces import HeadPoseEstimator

# Standard 3D reference face model (mm). Order matches the image points below.
_REFERENCE_FACE_3D = {
    "nose_tip": (0.0, 0.0, 0.0),
    "chin": (0.0, -63.6, -12.5),
    "left_eye_outer": (-46.5, 32.7, -26.0),
    "right_eye_outer": (46.5, 32.7, -26.0),
    "left_mouth": (-28.9, -63.5, -17.5),
    "right_mouth": (28.9, -63.5, -17.5),
}

# Landmark keys the estimator consumes (produced by MediaPipeFaceService).
_PNP_MAPPING = [
    ("nose_tip", "nose_tip"),
    ("chin", "chin"),
    ("left_eye_outer", "left_eye_outer"),
    ("right_eye_outer", "right_eye_outer"),
    ("left_mouth", "left_mouth"),
    ("right_mouth", "right_mouth"),
]


class PnPHeadPoseService(HeadPoseEstimator):
    name = "PNP"

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
                import cv2  # noqa: F401  ensures opencv availability
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
    def estimate(self, landmarks) -> Dict[str, Any]:
        """Estimate head pose from the MediaPipe 2D landmark dict.

        ``landmarks`` may be the dict produced by MediaPipeFaceService
        (keys nose_tip/chin/left_eye_outer/...). Coordinates may be normalized
        (0..1) or absolute pixels; the estimator normalizes internally.
        """
        if not self.is_loaded():
            self.load()
        if not self.is_loaded():
            return {"available": False, "error": self._error}

        import cv2
        import numpy as np

        # Normalize 2D points to pixels on a nominal canvas so focal length is
        # meaningful (f ~ image width). Values < 2 are treated as normalized.
        pts = []
        for key, src_key in _PNP_MAPPING:
            pt = landmarks.get(src_key)
            if pt is None:
                return {"available": False, "error": f"missing landmark {src_key}"}
            pts.append((float(pt[0]), float(pt[1])))

        max_coord = max(max(p[0], p[1]) for p in pts)
        scale = 1.0 if max_coord > 2.0 else 640.0
        image_points = [(x * scale, y * scale) for (x, y) in pts]
        w = max((x for x, y in image_points), default=640.0)
        h = max((y for x, y in image_points), default=640.0)

        model3d = np.array([list(_REFERENCE_FACE_3D[k]) for k, _ in _PNP_MAPPING], dtype=np.float64)
        img2d = np.array(image_points, dtype=np.float64).reshape(-1, 1, 2)
        camera_matrix = np.array(
            [[w, 0.0, w / 2.0],
             [0.0, w, h / 2.0],
             [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        try:
            success, rvec, tvec = cv2.solvePnP(model3d, img2d, camera_matrix, dist_coeffs)
            if not success:
                return {"available": False, "error": "solvePnP returned failure"}
        except cv2.error as exc:
            return {"available": False, "error": f"cv2.error: {exc}"}

        rmat, _ = cv2.Rodrigues(rvec)
        # Consistent angle extraction (proj2pj convention).
        proj = np.hstack((rmat.copy(), tvec.reshape(-1, 1)))
        euler = cv2.decomposeProjectionMatrix(proj)[-1]
        yaw, pitch, roll = (float(euler[i][0]) for i in range(3))

        return {
            "available": True,
            "yaw": round(yaw, 2),
            "pitch": round(pitch, 2),
            "roll": round(roll, 2),
            "points": len(image_points),
            "error": None,
        }

    # ------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        loaded = self.is_loaded() or self.load()
        return {
            "status": "ok" if loaded else "unavailable",
            "loaded": loaded,
            "implemented": True,
            "error": self._error,
        }


pnp_head_pose_service = PnPHeadPoseService()