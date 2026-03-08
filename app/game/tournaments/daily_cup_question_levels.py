from __future__ import annotations

_ROUND_1_LEVELS: tuple[str, ...] = ("A1", "A1", "A1", "A1", "A1", "A1", "A1")
_ROUND_2_LEVELS: tuple[str, ...] = ("A2", "A2", "A2", "A2", "A2", "A2", "A2")
_ROUND_3_LEVELS: tuple[str, ...] = ("A2", "A2", "A2", "A2", "B1", "B1", "B1")
_ROUND_4_LEVELS: tuple[str, ...] = ("B1", "B1", "B1", "B2", "B2", "B2", "B2")


def resolve_daily_cup_preferred_levels(
    *, round_no: int, duel_rounds: int
) -> tuple[str, ...] | None:
    if duel_rounds != 7:
        return None
    if round_no == 1:
        return _ROUND_1_LEVELS
    if round_no == 2:
        return _ROUND_2_LEVELS
    if round_no == 3:
        return _ROUND_3_LEVELS
    if round_no == 4:
        return _ROUND_4_LEVELS
    return None


__all__ = ["resolve_daily_cup_preferred_levels"]
