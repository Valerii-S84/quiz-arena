from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.game.tournaments.constants import TOURNAMENT_MATCH_STATUS_PENDING

ROUND_STATUSES = frozenset({"ROUND_1", "ROUND_2", "ROUND_3"})
_BERLIN_TZ = ZoneInfo("Europe/Berlin")


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


def format_deadline(deadline_utc: datetime | None) -> str:
    if deadline_utc is None:
        return "-"
    return deadline_utc.astimezone(_BERLIN_TZ).strftime("%d.%m %H:%M")


def format_tournament_format(format_code: str) -> str:
    return "12 Fragen" if format_code == "QUICK_12" else "5 Fragen"


def resolve_match_context(*, round_matches, viewer_user_id: int) -> tuple[str | None, int | None]:
    for match in round_matches:
        user_a = int(match.user_a)
        user_b = int(match.user_b) if match.user_b is not None else None
        if user_a != viewer_user_id and user_b != viewer_user_id:
            continue
        opponent_id = user_b if user_a == viewer_user_id else user_a
        if (
            user_b is not None
            and match.status == TOURNAMENT_MATCH_STATUS_PENDING
            and match.friend_challenge_id is not None
        ):
            return str(match.friend_challenge_id), opponent_id
        return None, opponent_id
    return None, None


def build_standings_lines(
    *,
    standings_user_ids: list[int],
    labels: dict[int, str],
    points_by_user: dict[int, str],
    viewer_user_id: int,
) -> list[str]:
    lines: list[str] = []
    for place, user_id in enumerate(standings_user_ids, start=1):
        medal = "🥇" if place == 1 else "🥈" if place == 2 else "🥉" if place == 3 else " "
        suffix = " (Du)" if user_id == viewer_user_id else ""
        lines.append(
            f"{place}. {medal} {labels.get(user_id, 'Spieler')}{suffix}"
            f" - {points_by_user.get(user_id, '0')} Pkt"
        )
    return lines


def build_round_text(
    *,
    tournament_name: str | None,
    tournament_format: str,
    round_no: int,
    deadline_text: str,
    opponent_label: str | None,
    standings_lines: list[str],
) -> str:
    header = f"🏆 {tournament_name}" if tournament_name else "🏆 Turnier mit Freunden"
    lines = [
        header,
        "",
        f"⚔️ Runde {round_no}/3 gestartet",
        f"Format: {format_tournament_format(tournament_format)}",
        f"Deadline: {deadline_text} (Berlin)",
    ]
    if opponent_label is None:
        lines.append("Gegner: Freilos")
    else:
        lines.append(f"Gegner: {opponent_label}")
    lines.extend(["", "📊 Tabelle", *standings_lines])
    return "\n".join(lines)


def build_completed_text(
    *,
    tournament_name: str | None,
    tournament_format: str,
    place: int,
    my_points: str,
    standings_lines: list[str],
) -> str:
    header = f"🏆 {tournament_name}" if tournament_name else "🏆 Turnier mit Freunden"
    lines = [
        header,
        "",
        "🏁 Turnier beendet!",
        f"Format: {format_tournament_format(tournament_format)}",
        f"Dein Ergebnis: Platz #{place} • {my_points} Pkt",
        "",
        "📊 Endtabelle",
        *standings_lines,
        "",
        "📤 Nutze 'Ergebnis teilen' fuer deinen Share-Link.",
    ]
    return "\n".join(lines)


def is_message_not_modified_error(exc: Exception) -> bool:
    return "message is not modified" in str(exc).lower()
