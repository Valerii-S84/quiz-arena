from __future__ import annotations

from app.core.config import get_settings


def is_canonical_duels_enabled() -> bool:
    return bool(get_settings().duels_rollout_enabled)
