"""Small in-memory per-principal rate limiter for sensitive endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            window = self._events[key]
            while window and now - window[0] > 60.0:
                window.popleft()
            if len(window) >= self.per_minute:
                return False
            window.append(now)
            return True
