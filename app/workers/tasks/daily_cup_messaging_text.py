from __future__ import annotations


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
    round_no: int,
    deadline_text: str,
    opponent_label: str | None,
    standings_lines: list[str],
) -> str:
    lines = [
        "🏆 Daily Arena Cup",
        "",
        f"⚔️ Runde {round_no}/3 gestartet",
        "Format: 5 Fragen",
        f"Deadline: {deadline_text} (Berlin)",
    ]
    lines.append("Gegner: Freilos" if opponent_label is None else f"Gegner: {opponent_label}")
    lines.extend(["", "📊 Tabelle", *standings_lines])
    return "\n".join(lines)


def build_completed_text(*, place: int, my_points: str, standings_lines: list[str]) -> str:
    lines = [
        "🏆 Daily Arena Cup",
        "",
        "🏁 Cup beendet!",
        f"Dein Ergebnis: Platz #{place} • {my_points} Pkt",
        "",
        "📊 Endtabelle",
        *standings_lines,
        "",
        "📤 Nutze 'Ergebnis teilen' fuer deinen Share-Link.",
    ]
    return "\n".join(lines)
