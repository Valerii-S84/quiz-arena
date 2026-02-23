from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.start_helpers import _notify_creator_about_join, _resolve_opponent_label
from app.bot.handlers.start_parsing import _extract_friend_challenge_token, _extract_start_payload
from app.bot.handlers.start_views import (
    _build_friend_plan_text,
    _build_friend_score_text,
    _build_friend_ttl_text,
    _build_home_text,
    _build_question_text,
)
from app.bot.keyboards.friend_challenge import build_friend_challenge_back_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.offers.service import OfferLoggingError, OfferService
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import GameSessionService
from app.services.user_onboarding import UserOnboardingService


async def handle_start_message(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"])
        return

    now_utc = datetime.now(timezone.utc)
    offer_selection = None
    start_payload = _extract_start_payload(message.text)
    friend_invite_token = _extract_friend_challenge_token(start_payload)
    challenge_start = None
    challenge_joined_now = False
    challenge_error_key: str | None = None
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=message.from_user,
            start_payload=start_payload,
        )
        if friend_invite_token is not None:
            try:
                join_result = await GameSessionService.join_friend_challenge_by_token(
                    session,
                    user_id=snapshot.user_id,
                    invite_token=friend_invite_token,
                    now_utc=now_utc,
                )
                challenge = join_result.snapshot
                challenge_joined_now = join_result.joined_now
                challenge_start = await GameSessionService.start_friend_challenge_round(
                    session,
                    user_id=snapshot.user_id,
                    challenge_id=challenge.challenge_id,
                    idempotency_key=f"start:friend:join:{challenge.challenge_id}:{message.message_id}",
                    now_utc=now_utc,
                )
            except (
                FriendChallengeNotFoundError,
                FriendChallengeCompletedError,
                FriendChallengeAccessError,
            ):
                challenge_error_key = "msg.friend.challenge.invalid"
            except FriendChallengeExpiredError:
                challenge_error_key = "msg.friend.challenge.expired"
            except FriendChallengeFullError:
                challenge_error_key = "msg.friend.challenge.full"
        else:
            try:
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:start:{message.from_user.id}:{message.message_id}",
                    now_utc=now_utc,
                )
            except OfferLoggingError:
                offer_selection = None

    if friend_invite_token is not None:
        if challenge_error_key is not None or challenge_start is None:
            await message.answer(
                TEXTS_DE[challenge_error_key or "msg.friend.challenge.invalid"],
                reply_markup=build_home_keyboard(),
            )
            return

        if challenge_joined_now:
            await _notify_creator_about_join(
                message,
                challenge=challenge_start.snapshot,
                joiner_user_id=snapshot.user_id,
            )

        opponent_label = await _resolve_opponent_label(
            challenge=challenge_start.snapshot,
            user_id=snapshot.user_id,
        )
        summary_lines = [
            TEXTS_DE["msg.friend.challenge.joined"],
            TEXTS_DE["msg.friend.challenge.with"].format(opponent_label=opponent_label),
            _build_friend_plan_text(total_rounds=challenge_start.snapshot.total_rounds),
            TEXTS_DE["msg.friend.challenge.play.instant"].format(
                total_rounds=challenge_start.snapshot.total_rounds
            ),
            _build_friend_score_text(
                challenge=challenge_start.snapshot,
                user_id=snapshot.user_id,
                opponent_label=opponent_label,
            ),
        ]
        ttl_text = _build_friend_ttl_text(challenge=challenge_start.snapshot, now_utc=now_utc)
        if ttl_text is not None:
            summary_lines.append(ttl_text)
        if challenge_start.waiting_for_opponent:
            summary_lines.append(TEXTS_DE["msg.friend.challenge.waiting"])
        if challenge_start.already_answered_current_round:
            summary_lines.append(TEXTS_DE["msg.friend.challenge.round.already.answered"])
        await message.answer(
            "\n".join(summary_lines),
            reply_markup=build_friend_challenge_back_keyboard(),
        )
        if challenge_start.start_result is not None:
            question_text = _build_question_text(
                source="FRIEND_CHALLENGE",
                snapshot_free_energy=snapshot.free_energy,
                snapshot_paid_energy=snapshot.paid_energy,
                start_result=challenge_start.start_result,
            )
            await message.answer(
                question_text,
                reply_markup=build_quiz_keyboard(
                    session_id=str(challenge_start.start_result.session.session_id),
                    options=challenge_start.start_result.session.options,
                ),
                parse_mode="HTML",
            )
        return

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await message.answer(response_text, reply_markup=build_home_keyboard())
    if offer_selection is not None:
        await message.answer(
            TEXTS_DE[offer_selection.text_key],
            reply_markup=build_offer_keyboard(offer_selection),
        )


async def handle_shop_open(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(
            TEXTS_DE["msg.shop.title"], reply_markup=build_shop_keyboard()
        )
    await callback.answer()


async def handle_home_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await callback.message.answer(response_text, reply_markup=build_home_keyboard())
    await callback.answer()
