from __future__ import annotations

from collections import deque
from threading import Lock

_LOGIN_FAILED_ATTEMPTS: dict[str, deque[float]] = {}
_LOGIN_THROTTLE_LOCK = Lock()
