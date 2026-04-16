from __future__ import annotations

import hashlib

from .constants import (
    MIX_STEP_WEIGHTS,
    MODE_PROGRESSION_CONFIGS,
    PERSISTENT_ADAPTIVE_LEVEL_CHAIN,
    ModeProgressionConfig,
)

LEVEL_CHAIN = PERSISTENT_ADAPTIVE_LEVEL_CHAIN
MAX_MIX_STEP = max(MIX_STEP_WEIGHTS)


def _mode_progression_config(mode: str) -> ModeProgressionConfig:
    return MODE_PROGRESSION_CONFIGS[mode]


def _normalize_chain_level(level: str | None) -> str:
    if level is None:
        return LEVEL_CHAIN[0]
    normalized = level.strip().upper()
    if normalized not in LEVEL_CHAIN:
        return LEVEL_CHAIN[0]
    return normalized


def _next_chain_level(level: str) -> str | None:
    current_index = LEVEL_CHAIN.index(level)
    if current_index >= len(LEVEL_CHAIN) - 1:
        return None
    return LEVEL_CHAIN[current_index + 1]


def get_allowed_levels(current_level: str, mix_step: int = 0) -> tuple[str, ...]:
    normalized = _normalize_chain_level(current_level)
    next_level = _next_chain_level(normalized)
    if mix_step <= 0 or next_level is None:
        return (normalized,)
    return (normalized, next_level)


def select_level_weighted(
    current_level: str,
    mix_step: int,
    *,
    selection_seed: str,
) -> str:
    normalized = _normalize_chain_level(current_level)
    next_level = _next_chain_level(normalized)
    if next_level is None:
        return normalized

    next_weight = MIX_STEP_WEIGHTS.get(mix_step, 0.0)
    if next_weight <= 0:
        return normalized

    digest = hashlib.sha256(selection_seed.encode("utf-8")).digest()
    roll = int.from_bytes(digest[:8], "big") / 2**64
    return next_level if roll < next_weight else normalized
