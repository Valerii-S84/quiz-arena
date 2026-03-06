from __future__ import annotations

from app.bot.texts.de import TEXTS_DE
from app.game.tournaments.constants import TOURNAMENT_SELF_BOT_LABEL


def build_standings_lines(
    *,
    standings_user_ids: list[int],
    labels: dict[int, str],
    points_by_user: dict[int, str],
    viewer_user_id: int,
    tie_breaks_by_user: dict[int, str] | None = None,
) -> list[str]:
    lines: list[str] = []
    for place, user_id in enumerate(standings_user_ids, start=1):
        medal = "🥇" if place == 1 else "🥈" if place == 2 else "🥉" if place == 3 else " "
        suffix = " (Du)" if user_id == viewer_user_id else ""
        tie_break_suffix = ""
        if tie_breaks_by_user is not None:
            tie_break_suffix = f" · TB {tie_breaks_by_user.get(user_id, '0')}"
        lines.append(
            f"{place}. {medal} {labels.get(user_id, 'Spieler')}{suffix}"
            f" - {points_by_user.get(user_id, '0')} Pkt{tie_break_suffix}"
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
    if opponent_label is None:
        lines.append(f"Gegner: {TOURNAMENT_SELF_BOT_LABEL}")
    else:
        lines.append(f"Gegner: {opponent_label}")
    lines.extend(["", "📊 Tabelle", *standings_lines])
    return "\n".join(lines)


def build_completed_text(*, place: int, my_points: str, standings_lines: list[str]) -> str:
    top_3 = standings_lines[:3]
    while len(top_3) < 3:
        top_3.append("—")
    final_summary = TEXTS_DE["msg.daily_cup.final_results"].format(
        top_1=top_3[0],
        top_2=top_3[1],
        top_3=top_3[2],
        place=place,
        score=my_points,
    )
    lines = [
        "🏆 Daily Arena Cup",
        "",
        final_summary,
        "",
        "📊 Endtabelle",
        *standings_lines,
        "",
        "📤 Nutze 'Ergebnis teilen' fuer deinen Share-Link.",
    ]
    return "\n".join(lines)
