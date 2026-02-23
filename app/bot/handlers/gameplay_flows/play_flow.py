from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
    ModeLockedError,
)
from app.game.sessions.types import AnswerSessionResult, FriendChallengeRoundStartResult


async def start_mode(
    callback: CallbackQuery,
    *,
    mode_code: str,
    source: str,
    idempotency_key: str,
    session_local,
    user_onboarding_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    trg_locked_mode_click: str,
    build_question_text,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)

    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            result = await game_session_service.start_session(
                session,
                user_id=snapshot.user_id,
                mode_code=mode_code,
                source=source,
                idempotency_key=idempotency_key,
                now_utc=now_utc,
            )
        except ModeLockedError:
            offer_selection = None
            try:
                offer_selection = await offer_service.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:locked:{callback.id}",
                    now_utc=now_utc,
                    trigger_event=trg_locked_mode_click,
                )
            except offer_logging_error:
                offer_selection = None

            text = (
                TEXTS_DE[offer_selection.text_key]
                if offer_selection is not None
                else TEXTS_DE["msg.locked.mode"]
            )
            keyboard = (
                build_offer_keyboard(offer_selection)
                if offer_selection is not None
                else build_home_keyboard()
            )
            await callback.message.answer(text, reply_markup=keyboard)
            await callback.answer()
            return
        except EnergyInsufficientError:
            offer_selection = None
            try:
                offer_selection = await offer_service.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:energy:{callback.id}",
                    now_utc=now_utc,
                )
            except offer_logging_error:
                offer_selection = None

            text = (
                TEXTS_DE[offer_selection.text_key]
                if offer_selection is not None
                else TEXTS_DE["msg.energy.empty.body"]
            )
            keyboard = (
                build_offer_keyboard(offer_selection)
                if offer_selection is not None
                else build_home_keyboard()
            )
            await callback.message.answer(text, reply_markup=keyboard)
            await callback.answer()
            return
        except DailyChallengeAlreadyPlayedError:
            await callback.message.answer(TEXTS_DE["msg.daily.challenge.used"], reply_markup=build_home_keyboard())
            await callback.answer()
            return

    question_text = build_question_text(
        source=source,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=result,
    )

    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(result.session.session_id),
            options=result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


async def send_friend_round_question(
    callback: CallbackQuery,
    *,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    round_start: FriendChallengeRoundStartResult,
    build_question_text,
) -> None:
    if callback.message is None or round_start.start_result is None:
        return

    question_text = build_question_text(
        source="FRIEND_CHALLENGE",
        snapshot_free_energy=snapshot_free_energy,
        snapshot_paid_energy=snapshot_paid_energy,
        start_result=round_start.start_result,
    )
    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(round_start.start_result.session.session_id),
            options=round_start.start_result.session.options,
        ),
        parse_mode="HTML",
    )


async def continue_regular_mode_after_answer(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    session_local,
    user_onboarding_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    build_question_text,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            next_result = await game_session_service.start_session(
                session,
                user_id=snapshot.user_id,
                mode_code=result.mode_code,
                source=result.source,
                idempotency_key=f"start:auto:{result.mode_code}:{callback.id}",
                now_utc=now_utc,
                preferred_question_level=result.next_preferred_level,
            )
        except ModeLockedError:
            await callback.message.answer(TEXTS_DE["msg.locked.mode"], reply_markup=build_home_keyboard())
            await callback.answer()
            return
        except EnergyInsufficientError:
            offer_selection = None
            try:
                offer_selection = await offer_service.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:energy:auto:{callback.id}",
                    now_utc=now_utc,
                )
            except offer_logging_error:
                offer_selection = None

            text = (
                TEXTS_DE[offer_selection.text_key]
                if offer_selection is not None
                else TEXTS_DE["msg.energy.empty.body"]
            )
            keyboard = (
                build_offer_keyboard(offer_selection)
                if offer_selection is not None
                else build_home_keyboard()
            )
            await callback.message.answer(text, reply_markup=keyboard)
            await callback.answer()
            return

    question_text = build_question_text(
        source=result.source,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=next_result,
    )
    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(next_result.session.session_id),
            options=next_result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


FRIEND_CHALLENGE_START_ERRORS = (
    FriendChallengeNotFoundError,
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeFullError,
)

FRIEND_CHALLENGE_EXPIRED_ERROR = FriendChallengeExpiredError
