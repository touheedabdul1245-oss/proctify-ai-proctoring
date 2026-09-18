"""
Cooldown gate (pure, Stage 3).

Suppresses duplicate "sustained-run" graduates so a single behaviour cannot
flood the engine with a stream of nearly-identical repeats. Cooldown is
PER-FAMILY: while family ``PHONE_USE`` is cooling down, ``SPEECH`` etc. remain
free to graduate.

    gate.can_fire("PHONE_USE") -> bool
    gate.arm("PHONE_USE")       # start the cooldown timer (thread-safe)

Inject ``now_fn`` for deterministic tests.
"""
import threading
import time
from typing import Dict, Optional

from .constants import COOLDOWN_BY_FAMILY

_time = time


class CooldownGate:
    def __init__(self, cooldown_by_family: Optional[Dict[str, float]] = None,
                 now_fn=None):
        self._cooldown = dict(cooldown_by_family or COOLDOWN_BY_FAMILY)
        self._now = now_fn or _monotonic
        self._lock = threading.Lock()
        self._until: Dict[str, float] = {}

    def can_fire(self, family: str) -> bool:
        now = self._now()
        with self._lock:
            return now >= self._until.get(family, 0.0)

    def arm(self, family: str) -> None:
        now = self._now()
        seconds = self._cooldown.get(family, self._cooldown.get("*", 15.0))
        with self._lock:
            self._until[family] = now + seconds

    def reset(self) -> None:
        with self._lock:
            self._until.clear()

    def remaining(self, family: str) -> float:
        now = self._now()
        with self._lock:
            return max(0.0, round(self._until.get(family, 0.0) - now, 3))


def _monotonic() -> float:
    return _time.monotonic()
