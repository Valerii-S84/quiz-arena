from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
)


async def handle_friend_challenge_series_best3(
    callback: CallbackQuery,
    *,
    friend_series_best3_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    friend_opponent_user_id,
    notify_opponent,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    challenge_id = parse_uuid_callback(pattern=friend_series_best3_re, callback_data=callback.data)
    if challenge_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            series_duel = await game_session_service.create_friend_challenge_best_of_three(
                session,
                initiator_user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
                best_of=3,
            )
        except FriendChallengePaymentRequiredError:
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(),
            )
            await callback.answer()
            return
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
        ):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return

    opponent_label = await resolve_opponent_label(
        challenge=series_duel,
        user_id=snapshot.user_id,
    )
    await callback.message.answer(
        "\n".join(
            [
                TEXTS_DE["msg.friend.challenge.series.started"].format(
                    opponent_label=opponent_label
                ),
                build_friend_plan_text(total_rounds=series_duel.total_rounds),
                build_series_progress_text(
                    game_no=series_duel.series_game_number,
                    best_of=series_duel.series_best_of,
                    my_wins=0,
                    opponent_wins=0,
                    opponent_label=opponent_label,
                ),
            ]
        ),
        reply_markup=build_friend_challenge_next_keyboard(
            challenge_id=str(series_duel.challenge_id)
        ),
    )
    opponent_user_id = friend_opponent_user_id(challenge=series_duel, user_id=snapshot.user_id)
    if opponent_user_id is not None:
        opponent_label_for_opponent = await resolve_opponent_label(
            challenge=series_duel,
            user_id=opponent_user_id,
        )
        await notify_opponent(
            callback,
            opponent_user_id=opponent_user_id,
            text="\n".join(
                [
                    TEXTS_DE["msg.friend.challenge.series.started"].format(
                        opponent_label=opponent_label_for_opponent
                    ),
                    build_friend_plan_text(total_rounds=series_duel.total_rounds),
                    build_series_progress_text(
                        game_no=series_duel.series_game_number,
                        best_of=series_duel.series_best_of,
                        my_wins=0,
                        opponent_wins=0,
                        opponent_label=opponent_label_for_opponent,
                    ),
                ]
            ),
            reply_markup=build_friend_challenge_next_keyboard(
                challenge_id=str(series_duel.challenge_id)
            ),
        )
    await callback.answer()


async def handle_friend_challenge_series_next(
    callback: CallbackQuery,
    *,
    friend_series_next_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    friend_opponent_user_id,
    notify_opponent,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    challenge_id = parse_uuid_callback(pattern=friend_series_next_re, callback_data=callback.data)
    if challenge_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            next_duel = await game_session_service.create_friend_challenge_series_next_game(
                session,
                initiator_user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
            my_wins, opponent_wins, game_no, best_of = (
                await game_session_service.get_friend_series_score_for_user(
                    session,
                    user_id=snapshot.user_id,
                    challenge_id=next_duel.challenge_id,
                    now_utc=now_utc,
                )
            )
        except FriendChallengePaymentRequiredError:
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(),
            )
            await callback.answer()
            return
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
        ):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return

    opponent_label = await resolve_opponent_label(
        challenge=next_duel,
        user_id=snapshot.user_id,
    )
    await callback.message.answer(
        "\n".join(
            [
                build_series_progress_text(
                    game_no=game_no,
                    best_of=best_of,
                    my_wins=my_wins,
                    opponent_wins=opponent_wins,
                    opponent_label=opponent_label,
                ),
                build_friend_plan_text(total_rounds=next_duel.total_rounds),
            ]
        ),
        reply_markup=build_friend_challenge_next_keyboard(challenge_id=str(next_duel.challenge_id)),
    )
    opponent_user_id = friend_opponent_user_id(challenge=next_duel, user_id=snapshot.user_id)
    if opponent_user_id is not None:
        opponent_label_for_opponent = await resolve_opponent_label(
            challenge=next_duel,
            user_id=opponent_user_id,
        )
        await notify_opponent(
            callback,
            opponent_user_id=opponent_user_id,
            text="\n".join(
                [
                    build_series_progress_text(
                        game_no=game_no,
                        best_of=best_of,
                        my_wins=opponent_wins,
                        opponent_wins=my_wins,
                        opponent_label=opponent_label_for_opponent,
                    ),
                    build_friend_plan_text(total_rounds=next_duel.total_rounds),
                ]
            ),
            reply_markup=build_friend_challenge_next_keyboard(
                challenge_id=str(next_duel.challenge_id)
            ),
        )
    await callback.answer()
