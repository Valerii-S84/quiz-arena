from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic

_FAILED_ATTEMPTS: dict[str, deque[float]] = {}
_LOCK = Lock()


def _trim_attempts(attempts: deque[float], *, now: float, window_seconds: int) -> None:
    cutoff = now - max(1, int(window_seconds))
    while attempts and attempts[0] < cutoff:
        attempts.popleft()


def is_rate_limited(*, bucket: str, limit: int, window_seconds: int) -> bool:
    resolved_limit = max(1, int(limit))
    now = monotonic()
    with _LOCK:
        attempts = _FAILED_ATTEMPTS.get(bucket)
        if attempts is None:
            return False
        _trim_attempts(attempts, now=now, window_seconds=window_seconds)
        if not attempts:
            _FAILED_ATTEMPTS.pop(bucket, None)
            return False
        return len(attempts) >= resolved_limit


def record_failure(*, bucket: str, window_seconds: int) -> None:
    now = monotonic()
    with _LOCK:
        attempts = _FAILED_ATTEMPTS.setdefault(bucket, deque())
        _trim_attempts(attempts, now=now, window_seconds=window_seconds)
        attempts.append(now)


def clear_failures(*, bucket: str) -> None:
    with _LOCK:
        _FAILED_ATTEMPTS.pop(bucket, None)
