from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.tournament_views import format_points
from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard
from app.workers.tasks.tournaments_messaging_text import format_deadline


def _build_roster_lines(
    *, participant_labels: list[tuple[int, str]], viewer_user_id: int
) -> list[str]:
    lines = [f"Teilnehmer: {len(participant_labels)}", ""]
    for user_id, label in participant_labels:
        suffix = " (Du)" if user_id == viewer_user_id else ""
        lines.append(f"• {label} ✅{suffix}")
    if viewer_user_id not in {user_id for user_id, _ in participant_labels}:
        lines.append("• Du?")
    return lines


def _build_standings_lines(
    *,
    participant_labels: list[tuple[int, str]],
    participant_points: dict[int, str],
    viewer_user_id: int,
) -> list[str]:
    lines: list[str] = []
    for index, (user_id, label) in enumerate(participant_labels, start=1):
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else " "
        you = " (Du)" if user_id == viewer_user_id else ""
        points = participant_points.get(user_id, "0")
        lines.append(f"{index}. {medal} {label}{you} - {points} Pkt")
    return lines


async def render_daily_cup_lobby(
    callback: CallbackQuery,
    *,
    lobby,
    user_id: int,
    labels: dict[int, str],
) -> None:
    if callback.message is None:
        return
    participant_labels = [
        (item.user_id, labels.get(item.user_id, "Spieler")) for item in lobby.participants
    ]
    body_lines = [
        "🏆 Daily Arena Cup",
        "",
        "Format: 5 Fragen • 3 Runden",
    ]
    if lobby.tournament.status == "REGISTRATION":
        body_lines.extend(
            _build_roster_lines(participant_labels=participant_labels, viewer_user_id=user_id)
        )
    else:
        round_no = max(1, int(lobby.tournament.current_round))
        body_lines.extend(
            [
                f"Runde {round_no}/3",
                f"Deadline: {format_deadline(lobby.tournament.round_deadline)} (Berlin)",
                "",
            ]
        )
        points_map = {item.user_id: format_points(item.score) for item in lobby.participants}
        body_lines.extend(
            _build_standings_lines(
                participant_labels=participant_labels,
                participant_points=points_map,
                viewer_user_id=user_id,
            )
        )

    play_challenge_id = (
        str(lobby.viewer_current_match_challenge_id)
        if lobby.viewer_current_match_challenge_id is not None
        else None
    )
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id=str(lobby.tournament.tournament_id),
        can_join=lobby.tournament.status == "REGISTRATION" and not lobby.viewer_joined,
        play_challenge_id=play_challenge_id,
        show_share_result=lobby.tournament.status == "COMPLETED" and lobby.viewer_joined,
    )
    await callback.message.answer("\n".join(body_lines), reply_markup=keyboard)
