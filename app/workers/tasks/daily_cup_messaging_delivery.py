from __future__ import annotations

from typing import Any

from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.workers.tasks.daily_cup_messaging_text import (
    build_completed_text,
    build_round_text,
    build_standings_lines,
)
from app.workers.tasks.tournaments_messaging_text import (
    format_deadline,
    is_message_not_modified_error,
    resolve_match_context,
)


async def deliver_daily_cup_messages(
    *,
    bot: Any,
    tournament: Tournament,
    round_matches: list[TournamentMatch],
    standings_user_ids: list[int],
    labels: dict[int, str],
    telegram_targets: dict[int, int],
    points_by_user: dict[int, str],
    tie_breaks_by_user: dict[int, str],
    place_by_user: dict[int, int],
    participant_rows: dict[int, TournamentParticipant],
    participants_total: int,
) -> dict[str, Any]:
    sent = edited = failed = 0
    new_message_ids: dict[int, int] = {}
    replaced_message_ids: dict[int, int] = {}

    for user_id in standings_user_ids:
        chat_id = telegram_targets.get(user_id)
        if chat_id is None:
            failed += 1
            continue

        play_challenge_id, opponent_user_id = resolve_match_context(
            round_matches=round_matches,
            viewer_user_id=user_id,
        )
        standings_lines = build_standings_lines(
            standings_user_ids=standings_user_ids,
            labels=labels,
            points_by_user=points_by_user,
            viewer_user_id=user_id,
            tie_breaks_by_user=tie_breaks_by_user if tournament.status == "COMPLETED" else None,
        )
        if tournament.status == "COMPLETED":
            text = build_completed_text(
                place=place_by_user[user_id],
                my_points=points_by_user.get(user_id, "0"),
                standings_lines=standings_lines,
            )
        else:
            text = build_round_text(
                round_no=max(1, int(tournament.current_round)),
                deadline_text=format_deadline(tournament.round_deadline),
                opponent_label=(
                    labels.get(opponent_user_id) if opponent_user_id is not None else None
                ),
                standings_lines=standings_lines,
            )
        keyboard = build_daily_cup_lobby_keyboard(
            tournament_id=str(tournament.id),
            can_join=False,
            play_challenge_id=play_challenge_id,
            play_button_text="Runde starten",
            show_share_result=tournament.status == "COMPLETED",
            show_proof_card=tournament.status == "COMPLETED",
            share_url=(
                build_daily_cup_share_url(
                    base_link=public_bot_link(),
                    share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
                        place=place_by_user[user_id],
                        total=participants_total,
                        points=points_by_user.get(user_id, "0"),
                    ),
                )
                if tournament.status == "COMPLETED"
                else None
            ),
        )
        existing_message_id = participant_rows[user_id].standings_message_id
        if existing_message_id is None:
            message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            sent += 1
            new_message_ids[user_id] = int(message.message_id)
            continue
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(existing_message_id),
                text=text,
                reply_markup=keyboard,
            )
            edited += 1
        except Exception as exc:
            if is_message_not_modified_error(exc):
                edited += 1
                continue
            message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            sent += 1
            replaced_message_ids[user_id] = int(message.message_id)

    return {
        "sent": sent,
        "edited": edited,
        "failed": failed,
        "new_message_ids": new_message_ids,
        "replaced_message_ids": replaced_message_ids,
    }
