from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_finished_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import AnswerSessionResult

from app.bot.handlers.gameplay_flows.friend_answer_completion_flow import (
    handle_completed_friend_challenge,
)


async def handle_friend_answer_branch(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    notify_opponent,
    friend_opponent_user_id,
    build_friend_score_text,
    build_friend_ttl_text,
    build_friend_finish_text,
    build_public_badge_label,
    build_friend_proof_card_text,
    build_series_progress_text,
    send_friend_round_question,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

    if result.friend_challenge is None:
        await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
        await callback.answer()
        return

    challenge = result.friend_challenge
    opponent_label = await resolve_opponent_label(
        challenge=challenge,
        user_id=snapshot.user_id,
    )
    await callback.message.answer(
        build_friend_score_text(
            challenge=challenge,
            user_id=snapshot.user_id,
            opponent_label=opponent_label,
        )
    )
    ttl_text = build_friend_ttl_text(challenge=challenge, now_utc=now_utc)
    if ttl_text is not None:
        await callback.message.answer(ttl_text)

    opponent_user_id = friend_opponent_user_id(challenge=challenge, user_id=snapshot.user_id)
    if result.friend_challenge_round_completed:
        round_result_text = TEXTS_DE["msg.friend.challenge.round.result"].format(
            round_no=(result.friend_challenge_answered_round or challenge.current_round)
        )
        await callback.message.answer(
            round_result_text,
        )
        if not result.idempotent_replay and opponent_user_id is not None:
            opponent_label_for_opponent = await resolve_opponent_label(
                challenge=challenge,
                user_id=opponent_user_id,
            )
            await notify_opponent(
                callback,
                opponent_user_id=opponent_user_id,
                text="\n".join(
                    [
                        build_friend_score_text(
                            challenge=challenge,
                            user_id=opponent_user_id,
                            opponent_label=opponent_label_for_opponent,
                        ),
                        round_result_text,
                    ]
                ),
            )

    if challenge.status in {"COMPLETED", "EXPIRED"}:
        await handle_completed_friend_challenge(
            callback,
            challenge=challenge,
            snapshot_user_id=snapshot.user_id,
            opponent_label=opponent_label,
            opponent_user_id=opponent_user_id,
            now_utc=now_utc,
            idempotent_replay=result.idempotent_replay,
            session_local=session_local,
            game_session_service=game_session_service,
            resolve_opponent_label=resolve_opponent_label,
            notify_opponent=notify_opponent,
            build_friend_score_text=build_friend_score_text,
            build_friend_finish_text=build_friend_finish_text,
            build_public_badge_label=build_public_badge_label,
            build_friend_proof_card_text=build_friend_proof_card_text,
            build_series_progress_text=build_series_progress_text,
        )
        await callback.answer()
        return

    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            round_start = await game_session_service.start_friend_challenge_round(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"start:friend:auto:{challenge.challenge_id}:{callback.id}",
                now_utc=now_utc,
            )
        except FriendChallengeExpiredError:
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.expired"],
                reply_markup=build_friend_challenge_finished_keyboard(
                    challenge_id=str(challenge.challenge_id)
                ),
            )
            await callback.answer()
            return
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
            FriendChallengeCompletedError,
            FriendChallengeFullError,
        ):
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
            await callback.answer()
            return

    if round_start.start_result is not None:
        await send_friend_round_question(
            callback,
            snapshot_free_energy=snapshot.free_energy,
            snapshot_paid_energy=snapshot.paid_energy,
            round_start=round_start,
        )
    else:
        waiting_text = TEXTS_DE["msg.friend.challenge.all_answered.waiting"].format(
            total_rounds=challenge.total_rounds,
            opponent_label=opponent_label,
        )
        await callback.message.answer(
            waiting_text,
            reply_markup=build_friend_challenge_back_keyboard(),
        )

    await callback.answer()
