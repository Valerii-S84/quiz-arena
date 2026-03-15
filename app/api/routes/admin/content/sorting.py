from __future__ import annotations

LEVEL_SORT_ORDER: dict[str, int] = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
    "C2": 6,
}


def _level_sort_key(level: str) -> tuple[int, str]:
    normalized = level.upper()
    return (LEVEL_SORT_ORDER.get(normalized, 99), normalized)
