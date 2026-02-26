from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()


def _clamp_hour(value: int) -> int:
    return max(0, min(23, int(value)))


def _clamp_minute(value: int) -> int:
    return max(0, min(59, int(value)))


def _clamp_batch_size(value: int) -> int:
    return max(1, min(1000, int(value)))


DAILY_PRECOMPUTE_HOUR_BERLIN = _clamp_hour(settings.daily_challenge_precompute_hour_berlin)
DAILY_PRECOMPUTE_MINUTE_BERLIN = _clamp_minute(settings.daily_challenge_precompute_minute_berlin)
DAILY_PUSH_HOUR_BERLIN = _clamp_hour(settings.daily_challenge_push_hour_berlin)
DAILY_PUSH_MINUTE_BERLIN = _clamp_minute(settings.daily_challenge_push_minute_berlin)
DAILY_PUSH_BATCH_SIZE = _clamp_batch_size(settings.daily_challenge_push_batch_size)

__all__ = [
    "DAILY_PRECOMPUTE_HOUR_BERLIN",
    "DAILY_PRECOMPUTE_MINUTE_BERLIN",
    "DAILY_PUSH_HOUR_BERLIN",
    "DAILY_PUSH_MINUTE_BERLIN",
    "DAILY_PUSH_BATCH_SIZE",
]
