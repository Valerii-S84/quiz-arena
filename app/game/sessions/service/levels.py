from __future__ import annotations

from .constants import FRIEND_CHALLENGE_LEVEL_SEQUENCE, LEVEL_ORDER, PERSISTENT_ADAPTIVE_MODE_BOUNDS


def _normalize_level(level: str | None) -> str | None:
    if level is None:
        return None
    normalized = level.strip().upper()
    return normalized or None


def _is_persistent_adaptive_mode(*, mode_code: str) -> bool:
    return mode_code in PERSISTENT_ADAPTIVE_MODE_BOUNDS


def _clamp_level_for_mode(*, mode_code: str, level: str | None) -> str | None:
    normalized = _normalize_level(level)
    bounds = PERSISTENT_ADAPTIVE_MODE_BOUNDS.get(mode_code)
    if bounds is None:
        return normalized

    min_level, max_level = bounds
    min_index = LEVEL_ORDER.index(min_level)
    max_index = LEVEL_ORDER.index(max_level)
    if normalized is None or normalized not in LEVEL_ORDER:
        return LEVEL_ORDER[min_index]
    level_index = LEVEL_ORDER.index(normalized)
    clamped_index = min(max_index, max(min_index, level_index))
    return LEVEL_ORDER[clamped_index]


def _next_preferred_level(
    *,
    question_level: str | None,
    is_correct: bool,
    mode_code: str | None = None,
) -> str | None:
    normalized = _normalize_level(question_level)
    if normalized is None:
        return None
    if normalized not in LEVEL_ORDER:
        return None
    if not is_correct:
        next_level = normalized
    else:
        current_index = LEVEL_ORDER.index(normalized)
        if current_index >= len(LEVEL_ORDER) - 1:
            next_level = normalized
        else:
            next_level = LEVEL_ORDER[current_index + 1]

    if mode_code is None:
        return next_level
    return _clamp_level_for_mode(mode_code=mode_code, level=next_level)


def _friend_challenge_level_for_round(*, round_number: int) -> str | None:
    if round_number <= 0:
        return None
    if round_number <= len(FRIEND_CHALLENGE_LEVEL_SEQUENCE):
        return FRIEND_CHALLENGE_LEVEL_SEQUENCE[round_number - 1]
    return FRIEND_CHALLENGE_LEVEL_SEQUENCE[-1]
