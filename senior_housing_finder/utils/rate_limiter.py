"""
Simple token-bucket-ish rate limiter.

Thread-safe within a single process. Use one instance per remote service to
avoid getting blocked. Pair with `tenacity` retries for resilience.
"""
import time
import threading
from typing import Optional


class RateLimiter:
    def __init__(self, requests_per_second: float):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.min_interval = 1.0 / requests_per_second
        self._lock = threading.Lock()
        self._last_call: Optional[float] = None

    def wait(self) -> None:
        """Block until it's safe to make the next request."""
        with self._lock:
            now = time.monotonic()
            if self._last_call is not None:
                elapsed = now - self._last_call
                if elapsed < self.min_interval:
                    time.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()
