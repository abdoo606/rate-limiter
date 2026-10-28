"""Four classic rate limiting strategies, all clock-injectable for deterministic tests."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol


class Clock(Protocol):
    def now(self) -> float: ...


class MonotonicClock:
    """Default clock. Monotonic so NTP jumps cannot corrupt the buckets."""

    def now(self) -> float:
        return time.monotonic()


@dataclass(slots=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after: float = 0.0
    limit: int = 0

    def __bool__(self) -> bool:
        return self.allowed


class Limiter(Protocol):
    def hit(self, key: str, cost: int = 1) -> Decision: ...


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class TokenBucket:
    """Allows short bursts, refills at a steady rate. Good general-purpose default."""

    def __init__(
        self,
        rate: float,
        capacity: int,
        clock: Clock | None = None,
    ) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.clock = clock or MonotonicClock()
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, cost: int = 1) -> Decision:
        if cost > self.capacity:
            return Decision(False, 0, float("inf"), int(self.capacity))
        with self._lock:
            now = self.clock.now()
            bucket = self._buckets.get(key) or _Bucket(self.capacity, now)
            elapsed = now - bucket.updated
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.rate)
            bucket.updated = now
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                self._buckets[key] = bucket
                return Decision(True, int(bucket.tokens), 0.0, int(self.capacity))
            self._buckets[key] = bucket
            needed = cost - bucket.tokens
            return Decision(False, 0, needed / self.rate, int(self.capacity))


class SlidingWindow:
    """Log of timestamps - exact, memory grows with traffic per key."""

    def __init__(self, limit: int, window: float, clock: Clock | None = None) -> None:
        if limit <= 0 or window <= 0:
            raise ValueError("limit and window must be positive")
        self.limit = limit
        self.window = float(window)
        self.clock = clock or MonotonicClock()
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, cost: int = 1) -> Decision:
        with self._lock:
            now = self.clock.now()
            cutoff = now - self.window
            events = [t for t in self._events.get(key, []) if t > cutoff]
            if len(events) + cost <= self.limit:
                events.extend([now] * cost)
                self._events[key] = events
                return Decision(True, self.limit - len(events), 0.0, self.limit)
            self._events[key] = events
            retry = (events[0] + self.window - now) if events else self.window
            return Decision(False, max(0, self.limit - len(events)), max(retry, 0.0), self.limit)


class FixedWindow:
    """Cheapest option, but allows 2x the limit across a window boundary."""

    def __init__(self, limit: int, window: float, clock: Clock | None = None) -> None:
        self.limit = limit
        self.window = float(window)
        self.clock = clock or MonotonicClock()
        self._counts: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _window_start(self, now: float) -> float:
        return now - (now % self.window)

    def hit(self, key: str, cost: int = 1) -> Decision:
        with self._lock:
            now = self.clock.now()
            start = self._window_start(now)
            count, window_start = self._counts.get(key, (0, start))
            if window_start != start:
                count, window_start = 0, start
            if count + cost <= self.limit:
                count += cost
                self._counts[key] = (count, window_start)
                return Decision(True, self.limit - count, 0.0, self.limit)
            self._counts[key] = (count, window_start)
            return Decision(False, 0, window_start + self.window - now, self.limit)


class LeakyBucketQueue:
    """Constant drain rate, no bursts at all - protects a fragile downstream."""

    def __init__(self, rate: float, capacity: int, clock: Clock | None = None) -> None:
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.clock = clock or MonotonicClock()
        self._levels: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, cost: int = 1) -> Decision:
        with self._lock:
            now = self.clock.now()
            level, updated = self._levels.get(key, (0.0, now))
            level = max(0.0, level - (now - updated) * self.rate)
            if level + cost <= self.capacity:
                level += cost
                self._levels[key] = (level, now)
                return Decision(True, int(self.capacity - level), 0.0, int(self.capacity))
            self._levels[key] = (level, now)
            return Decision(False, 0, (level + cost - self.capacity) / self.rate, int(self.capacity))


@dataclass(slots=True)
class FakeClock:
    """Deterministic clock used in the test suite."""

    _now: float = 0.0
    advance: Callable[[float], None] = field(init=False, default=lambda s: None)

    def now(self) -> float:
        return self._now

    def tick(self, seconds: float) -> float:
        self._now += seconds
        return self._now
