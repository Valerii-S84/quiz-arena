from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import build_friend_challenge_finished_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError


class _Answerable(Protocol):
    async def answer(self, *args, **kwargs) -> object: ...


async def handle_completed_friend_challenge(
    callback: CallbackQuery,
    *,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    opponent_user_id: int | None,
    now_utc: datetime,
    idempotent_replay: bool,
    session_local,
    game_session_service,
    resolve_opponent_label,
    notify_opponent,
    build_friend_score_text,
    build_friend_finish_text,
    build_public_badge_label,
    build_friend_proof_card_text,
    enqueue_friend_challenge_proof_cards,
    build_series_progress_text,
) -> None:
    series_my_wins = 0
    series_opponent_wins = 0
    series_game_no = challenge.series_game_number
    series_best_of = challenge.series_best_of
    if challenge.series_id is not None and challenge.series_best_of > 1:
        async with session_local.begin() as session:
            try:
                (
                    series_my_wins,
                    series_opponent_wins,
                    series_game_no,
                    series_best_of,
                ) = await game_session_service.get_friend_series_score_for_user(
                    session,
                    user_id=snapshot_user_id,
                    challenge_id=challenge.challenge_id,
                    now_utc=now_utc,
                )
            except (
                FriendChallengeNotFoundError,
                FriendChallengeAccessError,
            ):
                series_my_wins = 0
                series_opponent_wins = 0
                series_game_no = challenge.series_game_number
                series_best_of = challenge.series_best_of

    wins_needed = max(1, (series_best_of // 2) + 1)
    series_finished = (
        series_best_of <= 1
        or series_my_wins >= wins_needed
        or series_opponent_wins >= wins_needed
        or series_game_no >= series_best_of
    )
    show_next_series_game = (
        challenge.series_id is not None and challenge.series_best_of > 1 and not series_finished
    )
    if series_my_wins > series_opponent_wins:
        champion_label = "Du"
    elif series_opponent_wins > series_my_wins:
        champion_label = opponent_label
    else:
        champion_label = "Unentschieden"

    my_finish_text = build_friend_finish_text(
        challenge=challenge,
        user_id=snapshot_user_id,
        opponent_label=opponent_label,
    )
    my_badge_label = build_public_badge_label(
        challenge=challenge,
        user_id=snapshot_user_id,
        series_my_wins=series_my_wins,
        series_opponent_wins=series_opponent_wins,
    )
    my_proof_card_text = build_friend_proof_card_text(
        challenge=challenge,
        user_id=snapshot_user_id,
        opponent_label=opponent_label,
    )
    finish_keyboard = build_friend_challenge_finished_keyboard(
        challenge_id=str(challenge.challenge_id),
        show_next_series_game=show_next_series_game,
    )
    my_message_lines = [my_finish_text]
    if challenge.series_best_of > 1:
        my_message_lines.append(
            build_series_progress_text(
                game_no=series_game_no,
                best_of=series_best_of,
                my_wins=series_my_wins,
                opponent_wins=series_opponent_wins,
                opponent_label=opponent_label,
            )
        )
        if series_finished:
            my_message_lines.append(
                TEXTS_DE["msg.friend.challenge.series.finished"].format(
                    champion_label=champion_label
                )
            )
    my_message_lines.append(
        TEXTS_DE["msg.friend.challenge.badge.public"].format(badge_label=my_badge_label)
    )
    my_message_lines.append("")
    my_message_lines.append(my_proof_card_text)
    message = callback.message
    assert message is not None
    assert hasattr(message, "answer")
    answerable = cast(_Answerable, message)
    await answerable.answer(
        "\n".join(my_message_lines),
        reply_markup=finish_keyboard,
    )
    if not idempotent_replay and opponent_user_id is not None:
        opponent_label_for_opponent = await resolve_opponent_label(
            challenge=challenge,
            user_id=opponent_user_id,
        )
        opponent_badge_label = build_public_badge_label(
            challenge=challenge,
            user_id=opponent_user_id,
            series_my_wins=series_opponent_wins,
            series_opponent_wins=series_my_wins,
        )
        opponent_proof_card_text = build_friend_proof_card_text(
            challenge=challenge,
            user_id=opponent_user_id,
            opponent_label=opponent_label_for_opponent,
        )
        opponent_finish_keyboard = build_friend_challenge_finished_keyboard(
            challenge_id=str(challenge.challenge_id),
            show_next_series_game=show_next_series_game,
        )
        opponent_message_lines = [
            build_friend_score_text(
                challenge=challenge,
                user_id=opponent_user_id,
                opponent_label=opponent_label_for_opponent,
            ),
            build_friend_finish_text(
                challenge=challenge,
                user_id=opponent_user_id,
                opponent_label=opponent_label_for_opponent,
            ),
        ]
        if challenge.series_best_of > 1:
            opponent_champion_label = champion_label
            if champion_label == "Du":
                opponent_champion_label = opponent_label_for_opponent
            elif champion_label == opponent_label:
                opponent_champion_label = "Du"
            opponent_message_lines.append(
                build_series_progress_text(
                    game_no=series_game_no,
                    best_of=series_best_of,
                    my_wins=series_opponent_wins,
                    opponent_wins=series_my_wins,
                    opponent_label=opponent_label_for_opponent,
                )
            )
            if series_finished:
                opponent_message_lines.append(
                    TEXTS_DE["msg.friend.challenge.series.finished"].format(
                        champion_label=opponent_champion_label
                    )
                )
        opponent_message_lines.append(
            TEXTS_DE["msg.friend.challenge.badge.public"].format(badge_label=opponent_badge_label)
        )
        opponent_message_lines.append("")
        opponent_message_lines.append(opponent_proof_card_text)
        await notify_opponent(
            callback,
            opponent_user_id=opponent_user_id,
            text="\n".join(opponent_message_lines),
            reply_markup=opponent_finish_keyboard,
        )
    if not idempotent_replay:
        enqueue_friend_challenge_proof_cards(challenge_id=str(challenge.challenge_id))
