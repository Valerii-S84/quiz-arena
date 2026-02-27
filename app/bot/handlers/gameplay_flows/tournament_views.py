from __future__ import annotations

from decimal import Decimal

from aiogram.types import CallbackQuery

from app.bot.keyboards.tournament import build_tournament_lobby_keyboard
from app.game.tournaments.constants import TOURNAMENT_STATUS_REGISTRATION


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


def format_format_label(format_code: str) -> str:
    return "12 Fragen" if format_code == "QUICK_12" else "5 Fragen"


def _build_roster_lines(
    *,
    participant_labels: list[tuple[int, str]],
    viewer_user_id: int,
    max_participants: int,
) -> list[str]:
    lines = [f"Teilnehmer: {len(participant_labels)}/{max_participants}", ""]
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


async def resolve_participant_labels(*, participants, users_repo, session) -> dict[int, str]:
    users = await users_repo.list_by_ids(session, [item.user_id for item in participants])
    labels: dict[int, str] = {}
    for user in users:
        labels[int(user.id)] = format_user_label(
            username=user.username,
            first_name=user.first_name,
        )
    return labels


async def render_tournament_lobby(
    callback: CallbackQuery,
    *,
    lobby,
    user_id: int,
    labels: dict[int, str],
    join_hint_invite_code: str | None = None,
) -> None:
    if callback.message is None:
        return
    participant_labels = [
        (item.user_id, labels.get(item.user_id, "Spieler")) for item in lobby.participants
    ]
    header = (
        f"🏆 {lobby.tournament.name}"
        if lobby.tournament.name
        else "🏆 Turnier mit Freunden"
    )
    body_lines = [
        header,
        "",
        f"Format: {format_format_label(lobby.tournament.format)} • 3 Runden",
    ]
    if lobby.tournament.status == TOURNAMENT_STATUS_REGISTRATION:
        body_lines.extend(
            _build_roster_lines(
                participant_labels=participant_labels,
                viewer_user_id=user_id,
                max_participants=lobby.tournament.max_participants,
            )
        )
    else:
        round_no = max(1, int(lobby.tournament.current_round))
        body_lines.append(f"Runde {round_no}/3")
        body_lines.append("")
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
    keyboard = build_tournament_lobby_keyboard(
        invite_code=(join_hint_invite_code or lobby.tournament.invite_code),
        tournament_id=str(lobby.tournament.tournament_id),
        can_join=(
            lobby.tournament.status == TOURNAMENT_STATUS_REGISTRATION
            and not lobby.viewer_joined
            and join_hint_invite_code is not None
        ),
        can_start=lobby.can_start,
        play_challenge_id=play_challenge_id,
        show_share_result=lobby.tournament.status == "COMPLETED" and lobby.viewer_joined,
    )
    await callback.message.answer("\n".join(body_lines), reply_markup=keyboard)
