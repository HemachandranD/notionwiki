"""Token-bucket limiter for Notion's ~3 req/s average rate limit (docs/design.md §5.1)."""

from __future__ import annotations

import threading
import time


class TokenBucket:
    """A simple thread-safe token bucket. `acquire()` blocks until a token is free."""

    def __init__(self, rate: float = 3.0, capacity: float = 3.0):
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, amount: float = 1.0) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                wait = (amount - self._tokens) / self.rate
            time.sleep(wait)
