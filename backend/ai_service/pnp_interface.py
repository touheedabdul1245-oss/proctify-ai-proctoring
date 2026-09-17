"""
PnP-based head-pose estimation.

Stage 1: integration contract only. Estimate yaw/pitch/roll from 2D
facial landmarks using solvePnP in Stage 3.
"""
from typing import Any, Dict

from .interfaces import HeadPoseEstimator


class PnPHeadPoseService(HeadPoseEstimator):
    name = "PNP"

    def __init__(self):
        self._loaded = False
        self._error = None

    def load(self) -> bool:
        # Stage 3: build the 3D reference face model + camera intrinsics,
        # and use cv2.solvePnP here.
        self._loaded = True
        return True

    def is_loaded(self) -> bool:
        return self._loaded

    def estimate(self, landmarks) -> Dict[str, Any]:
        raise NotImplementedError("Head-pose estimation arrives in Stage 3.")

    def health(self) -> Dict[str, Any]:
        return {
            "status": "available" if self.is_loaded() else "ready",
            "loaded": self.is_loaded(),
            "implemented": False,
            "note": "Integration contract only. PnP head-pose estimation in Stage 3.",
            "error": self._error,
        }


pnp_head_pose_service = PnPHeadPoseService()