"""
MediaPipe face / landmark processing (Stage 3).

Uses the EXISTING MediaPipe asset in read-only mode — nothing is downloaded,
trained or replaced:

* Preferred: the MediaPipe Tasks ``FaceLandmarker`` task file referenced by
  FACE_LANDMARKER_MODEL_PATH (from PROCTIFY_V2). It outputs 478 landmarks
  including iris points, which also feeds gaze estimation.
* Fallback: the bundled ``mediapipe.solutions.face_mesh`` model with
  ``refine_landmarks=True`` (same 478-point mesh).

The service returns structured per-face results for the proctoring engine:

    {
      "available": True,
      "face_count": N,
      "faces": [
        {
          "bbox": [x1, y1, x2, y2],                       # normalized 0..1 -> pixels done by observer
          "landmarks": {
             "nose_tip": [x, y],
             "chin": [x, y],
             "left_eye_outer": [x, y],   # image-left corner of subject's right eye (M.P. 33)
             "left_eye_inner": [x, y],   # M.P. 133
             "right_eye_inner": [x, y],  # M.P. 263
             "right_eye_outer": [x, y],  # M.P. 362
             "left_eye_center": [x, y],  # M.P. 468 (left iris)
             "right_eye_center": [x, y], # M.P. 473 (right iris)
             "left_mouth": [x, y],
             "right_mouth": [x, y],
          },
          "gaze": {
             "x": float,  # normalized horizontal gaze offset (-1..1)
             "y": float,  # normalized vertical gaze offset
             "iris_visible": bool,
          },
        }
      ],
      "error": None,
    }

Coordinates are NORMALIZED (0..1) like MediaPipe output; the observer scales
them to pixel space as needed.
"""
import os
import threading
from typing import Any, Dict, List, Optional

from ..config import (
    FACE_LANDMARKER_MODEL_PATH,
    MEDIAPIPE_MAX_FACES,
    MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
)
from .interfaces import FaceLandmarker

# FaceMesh 478-point indices used by this pipeline.
_MP_LEFT_EYE_OUTER = 33
_MP_LEFT_EYE_INNER = 133
_MP_RIGHT_EYE_INNER = 263
_MP_RIGHT_EYE_OUTER = 362
_MP_NOSE_TIP = 1
_MP_CHIN = 152
_MP_LEFT_MOUTH = 61
_MP_RIGHT_MOUTH = 291
_MP_LEFT_IRIS = 468
_MP_RIGHT_IRIS = 473


def _pt(lm) -> List[float]:
    return [float(lm.x), float(lm.y)]


def estimate_gaze(left_iris, right_iris, left_eye_inner, left_eye_outer,
                  right_eye_inner, right_eye_outer):
    """Return normalized horizontal/vertical gaze offset from iris positions.

    Positive ``x`` means the gaze is shifted toward the subject's right
    (image-left). The offset is normalized by the inter-eye distance so it is
    resolution independent. Returns None when iris landmarks are unavailable.
    """
    if not (left_iris and right_iris):
        return None
    eye_width = max(float(abs(right_eye_outer[0] - left_eye_outer[0])), 1e-6)
    eye_height = max(float(abs(right_eye_outer[1] - left_eye_outer[1])), 1e-6)
    inter_distance = max((eye_width ** 2 + eye_height ** 2) ** 0.5, 1e-6)

    left_eye_cx = (left_eye_inner[0] + left_eye_outer[0]) / 2.0
    left_eye_cy = (left_eye_inner[1] + left_eye_outer[1]) / 2.0
    right_eye_cx = (right_eye_inner[0] + right_eye_outer[0]) / 2.0
    right_eye_cy = (right_eye_inner[1] + right_eye_outer[1]) / 2.0

    gx_left = (left_iris[0] - left_eye_cx) / inter_distance
    gx_right = (right_iris[0] - right_eye_cx) / inter_distance
    gy_left = (left_iris[1] - left_eye_cy) / inter_distance
    gy_right = (right_iris[1] - right_eye_cy) / inter_distance

    return {
        "x": round((gx_left + gx_right) / 2.0, 4),
        "y": round((gy_left + gy_right) / 2.0, 4),
        "iris_visible": True,
    }


def _landmarks_from_mesh(landmarks) -> Dict[str, List[float]]:
    return {
        "nose_tip": _pt(landmarks[_MP_NOSE_TIP]),
        "chin": _pt(landmarks[_MP_CHIN]),
        "left_eye_outer": _pt(landmarks[_MP_LEFT_EYE_OUTER]),
        "left_eye_inner": _pt(landmarks[_MP_LEFT_EYE_INNER]),
        "right_eye_inner": _pt(landmarks[_MP_RIGHT_EYE_INNER]),
        "right_eye_outer": _pt(landmarks[_MP_RIGHT_EYE_OUTER]),
        "left_eye_center": _pt(landmarks[_MP_LEFT_IRIS]),
        "right_eye_center": _pt(landmarks[_MP_RIGHT_IRIS]),
        "left_mouth": _pt(landmarks[_MP_LEFT_MOUTH]),
        "right_mouth": _pt(landmarks[_MP_RIGHT_MOUTH]),
    }


class MediaPipeFaceService(FaceLandmarker):
    name = "MEDIAPIPE"

    def __init__(self):
        self._loaded = False
        self._error = None
        self._backend = "none"  # "tasks" | "face_mesh" | "none"
        self._tasks_landmarker = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Load / verify
    # ------------------------------------------------------------------
    def load(self) -> bool:
        with self._lock:
            if self._loaded:
                return True
            try:
                import mediapipe  # noqa: F401  (also triggers bundled assets check)
                mp_version_ok = hasattr(mediapipe, "solutions")
                # Prefer the Tasks API when the task file is present.
                tasks_ok = False
                if os.path.isfile(str(FACE_LANDMARKER_MODEL_PATH)):
                    try:
                        from mediapipe.tasks import python as mp_python
                        from mediapipe.tasks.python import vision
                        self._tasks_landmarker = vision.FaceLandmarker.create_from_options(
                            vision.FaceLandmarkerOptions(
                                base_options=mp_python.BaseOptions(
                                    model_asset_path=str(FACE_LANDMARKER_MODEL_PATH)
                                ),
                                running_mode=vision.RunningMode.IMAGE,
                                num_faces=MEDIAPIPE_MAX_FACES,
                                min_face_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
                                output_face_blendshapes=False,
                                output_facial_transformation_matrixes=False,
                            )
                        )
                        self._backend = "tasks"
                        tasks_ok = True
                    except Exception as exc:  # task file present but unusable
                        self._error = f"Tasks FaceLandmarker failed ({exc}); using face_mesh fallback."
                if not tasks_ok and mp_version_ok:
                    # Fallback: bundled solutions.face_mesh with iris refinement.
                    import mediapipe as mp
                    self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                        static_image_mode=False,
                        max_num_faces=MEDIAPIPE_MAX_FACES,
                        refine_landmarks=True,
                        min_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
                        min_tracking_confidence=0.5,
                    )
                    self._backend = "face_mesh"
                if self._backend == "none":
                    self._error = "MediaPipe is not importable on this machine."
                    return False
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
    # Processing
    # ------------------------------------------------------------------
    def process(self, frame) -> Dict[str, Any]:
        if not self.is_loaded():
            self.load()
        if not self.is_loaded():
            return {"available": False, "face_count": 0, "faces": [], "error": self._error}

        faces: List[Dict[str, Any]] = []
        try:
            normalized = frame  # cv2 BGR multichannel image
            if self._backend == "tasks":
                import numpy as np
                import mediapipe as mp
                rgb = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(cv2_bgr2rgb(normalized)))
                result = self._tasks_landmarker.detect(rgb)
                face_landmarks = list(getattr(result, "face_landmarks", []) or [])
                for flm in face_landmarks:
                    lms = list(flm)
                    faces.append(self._face_dict(_landmarks_from_mesh(lms), lms))
            else:
                rgb = cv2_bgr2rgb(normalized)
                results = self._face_mesh.process(rgb)
                if results.multi_face_landmarks:
                    for flm in results.multi_face_landmarks:
                        faces.append(self._face_dict(_landmarks_from_mesh(flm.landmark), list(flm.landmark)))
        except Exception as exc:
            return {"available": False, "face_count": 0, "faces": [], "error": f"{type(exc).__name__}: {exc}"}

        return {"available": True, "face_count": len(faces), "faces": faces, "error": None}

    def _face_dict(self, landmarks: Dict[str, List[float]], lms) -> Dict[str, Any]:
        gaze = estimate_gaze(
            landmarks["left_eye_center"], landmarks["right_eye_center"],
            landmarks["left_eye_inner"], landmarks["left_eye_outer"],
            landmarks["right_eye_inner"], landmarks["right_eye_outer"],
        )
        # Approximate bbox from landmark extremes (normalized coordinates).
        xs = [p[0] for p in landmarks.values()]
        ys = [p[1] for p in landmarks.values()]
        return {
            "bbox": [min(xs) - 0.05, min(ys) - 0.05, max(xs) + 0.05, max(ys) + 0.05],
            "landmarks": landmarks,
            "gaze": gaze,
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        loaded = self.is_loaded() or self.load()
        return {
            "status": "ok" if loaded else "unavailable",
            "loaded": loaded,
            "implemented": True,
            "backend": self._backend,
            "model_path": str(FACE_LANDMARKER_MODEL_PATH),
            "error": self._error,
        }


def cv2_bgr2rgb(frame):
    try:
        return frame[:, :, ::-1]
    except Exception:
        return frame


mediapipe_face_service = MediaPipeFaceService()