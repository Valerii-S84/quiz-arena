from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PremiumStatus:
    active: bool
    scope: str | None


_PREMIUM_STATUS_CACHE: ContextVar[dict[tuple[int, datetime], PremiumStatus] | None] = ContextVar(
    "premium_status_cache",
    default=None,
)


@contextmanager
def entitlement_request_cache() -> Iterator[None]:
    existing = _PREMIUM_STATUS_CACHE.get()
    if existing is not None:
        yield
        return

    token = _PREMIUM_STATUS_CACHE.set({})
    try:
        yield
    finally:
        _PREMIUM_STATUS_CACHE.reset(token)


def get_cached_premium_status(user_id: int, now_utc: datetime) -> PremiumStatus | None:
    cache = _PREMIUM_STATUS_CACHE.get()
    if cache is None:
        return None
    return cache.get((int(user_id), now_utc))


def store_cached_premium_status(
    user_id: int,
    now_utc: datetime,
    status: PremiumStatus,
) -> None:
    cache = _PREMIUM_STATUS_CACHE.get()
    if cache is not None:
        cache[(int(user_id), now_utc)] = status
