from __future__ import annotations

from decimal import Decimal


def format_user_label(*, username: str | None, first_name: str | None) -> str:
    if username:
        cleaned = username.strip()
        if cleaned:
            return f"@{cleaned}"
    if first_name:
        cleaned = first_name.strip()
        if cleaned:
            return cleaned
    return "Spieler"


def format_points(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f").rstrip("0").rstrip(".")


def build_caption(*, place: int, points: str) -> str:
    return f"🏆 Daily Arena Cup\nPlatz #{place}\nPunkte: {points}"
