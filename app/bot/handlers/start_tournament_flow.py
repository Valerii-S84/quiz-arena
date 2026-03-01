from __future__ import annotations

from aiogram.types import Message

from app.bot.handlers.gameplay_flows.tournament_views import format_points, format_user_label
from app.bot.keyboards.tournament import build_tournament_lobby_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings
from app.game.tournaments.errors import (
    TournamentAccessError,
    TournamentAlreadyStartedError,
    TournamentClosedError,
    TournamentNotFoundError,
)


async def handle_start_tournament_payload(
    message: Message,
    *,
    session,
    tournament_invite_code: str | None,
    viewer_user_id: int,
    tournament_service,
    users_repo,
) -> bool:
    if tournament_invite_code is None:
        return False
    try:
        lobby = await tournament_service.get_private_tournament_lobby_by_invite_code(
            session,
            invite_code=tournament_invite_code,
            viewer_user_id=viewer_user_id,
        )
    except (TournamentNotFoundError, TournamentAccessError):
        await message.answer(TEXTS_DE["msg.tournament.not_found"])
        return True
    except (TournamentClosedError, TournamentAlreadyStartedError):
        await message.answer(TEXTS_DE["msg.tournament.closed"])
        return True

    users = await users_repo.list_by_ids(session, [item.user_id for item in lobby.participants])
    labels = {
        int(user.id): format_user_label(username=user.username, first_name=user.first_name)
        for user in users
    }
    participant_lines = [
        f"• {labels.get(item.user_id, 'Spieler')} ✅"
        + (" (Du)" if item.user_id == viewer_user_id else "")
        for item in lobby.participants
    ]

    header = f"🏆 {lobby.tournament.name}" if lobby.tournament.name else "🏆 Turnier mit Freunden"
    body_lines = [
        header,
        "",
        f"Format: {'12 Fragen' if lobby.tournament.format == 'QUICK_12' else '5 Fragen'} • 3 Runden",
        f"Teilnehmer: {len(lobby.participants)}/{lobby.tournament.max_participants}",
        "",
    ]
    if participant_lines:
        body_lines.extend(participant_lines)
    if not lobby.viewer_joined:
        body_lines.append("• Du?")
    if lobby.tournament.status != "REGISTRATION":
        body_lines.extend(["", f"Runde {max(1, int(lobby.tournament.current_round))}/3", ""])
        for index, item in enumerate(lobby.participants, start=1):
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else " "
            body_lines.append(
                f"{index}. {medal} {labels.get(item.user_id, 'Spieler')} - {format_points(item.score)} Pkt"
            )

    play_challenge_id = (
        str(lobby.viewer_current_match_challenge_id)
        if lobby.viewer_current_match_challenge_id is not None
        else None
    )
    keyboard = build_tournament_lobby_keyboard(
        invite_code=lobby.tournament.invite_code,
        tournament_id=str(lobby.tournament.tournament_id),
        can_join=lobby.tournament.status == "REGISTRATION" and not lobby.viewer_joined,
        can_start=lobby.can_start,
        play_challenge_id=play_challenge_id,
        show_share_result=lobby.tournament.status == "COMPLETED" and lobby.viewer_joined,
    )
    welcome_image_file_id = get_settings().resolved_welcome_image_file_id
    should_show_join_photo = (
        bool(welcome_image_file_id)
        and lobby.tournament.status == "REGISTRATION"
        and not lobby.viewer_joined
    )
    if should_show_join_photo:
        creator_label = labels.get(
            int(lobby.tournament.created_by) if lobby.tournament.created_by is not None else -1,
            "Freund",
        )
        format_label = "12 Fragen" if lobby.tournament.format == "QUICK_12" else "5 Fragen"
        await message.answer_photo(
            photo=welcome_image_file_id,
            caption=(
                f"🏆 {creator_label}'s Turnier\n"
                f"Format: {format_label} • 3 Runden\n"
                f"Teilnehmer: {len(lobby.participants)}/{lobby.tournament.max_participants}"
            ),
            reply_markup=keyboard,
        )
        await message.answer("\n".join(body_lines))
        return True

    await message.answer("\n".join(body_lines), reply_markup=keyboard)
    return True
