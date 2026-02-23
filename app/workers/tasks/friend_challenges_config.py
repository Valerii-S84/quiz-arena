from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()

DEADLINE_BATCH_SIZE = max(1, int(settings.friend_challenge_deadline_batch_size))
LAST_CHANCE_SECONDS = max(60, int(settings.friend_challenge_last_chance_seconds))
SCAN_INTERVAL_SECONDS = max(30, int(settings.friend_challenge_deadline_scan_interval_seconds))

__all__ = ["DEADLINE_BATCH_SIZE", "LAST_CHANCE_SECONDS", "SCAN_INTERVAL_SECONDS"]
