from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.offers.constants import TRG_LOCKED_MODE_CLICK
from app.economy.offers.service import OfferLoggingError, OfferService
from app.game.modes.rules import is_zero_cost_source
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    InvalidAnswerOptionError,
    ModeLockedError,
    SessionNotFoundError,
)
from app.game.sessions.service import GameSessionService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="gameplay")

ANSWER_RE = re.compile(r"^answer:([0-9a-f\-]{36}):([0-3])$")


async def _start_mode(
    callback: CallbackQuery,
    *,
    mode_code: str,
    source: str,
    idempotency_key: str,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            result = await GameSessionService.start_session(
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
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:locked:{callback.id}",
                    now_utc=now_utc,
                    trigger_event=TRG_LOCKED_MODE_CLICK,
                )
            except OfferLoggingError:
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
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:energy:{callback.id}",
                    now_utc=now_utc,
                )
            except OfferLoggingError:
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

    question_text = "\n".join(
        [
            TEXTS_DE["msg.game.mode"].format(mode_code=result.session.mode_code),
            TEXTS_DE["msg.game.energy.left"].format(
                free_energy=(
                    snapshot.free_energy if is_zero_cost_source(source) else result.energy_free
                ),
                paid_energy=(
                    snapshot.paid_energy if is_zero_cost_source(source) else result.energy_paid
                ),
            ),
            result.session.text,
            TEXTS_DE["msg.game.choose_option"],
        ]
    )

    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(result.session.session_id),
            options=result.session.options,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "play")
async def handle_play(callback: CallbackQuery) -> None:
    await _start_mode(
        callback,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key=f"start:play:{callback.id}",
    )


@router.callback_query(F.data == "daily_challenge")
async def handle_daily_challenge(callback: CallbackQuery) -> None:
    await _start_mode(
        callback,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        idempotency_key=f"start:daily:{callback.id}",
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    mode_code = callback.data.split(":", maxsplit=1)[1]
    await _start_mode(
        callback,
        mode_code=mode_code,
        source="MENU",
        idempotency_key=f"start:mode:{mode_code}:{callback.id}",
    )


@router.callback_query(F.data.regexp(ANSWER_RE))
async def handle_answer(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    matched = ANSWER_RE.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    session_id = UUID(matched.group(1))
    selected_option = int(matched.group(2))
    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            result = await GameSessionService.submit_answer(
                session,
                user_id=snapshot.user_id,
                session_id=session_id,
                selected_option=selected_option,
                idempotency_key=f"answer:{callback.id}",
                now_utc=now_utc,
            )
        except SessionNotFoundError:
            await callback.message.answer(TEXTS_DE["msg.game.session.not_found"], reply_markup=build_home_keyboard())
            await callback.answer()
            return
        except InvalidAnswerOptionError:
            await callback.message.answer(TEXTS_DE["msg.system.error"])
            await callback.answer()
            return

    answer_key = "msg.game.answer.correct" if result.is_correct else "msg.game.answer.incorrect"
    response_lines = [TEXTS_DE[answer_key]]
    if result.selected_answer_text is not None:
        response_lines.append(
            TEXTS_DE["msg.game.answer.selected"].format(answer=result.selected_answer_text)
        )
    if result.correct_answer_text is not None:
        response_lines.append(
            TEXTS_DE["msg.game.answer.correct_label"].format(answer=result.correct_answer_text)
        )
    response_lines.append(
        TEXTS_DE["msg.game.streak"].format(
            current_streak=result.current_streak,
            best_streak=result.best_streak,
        )
    )
    response = "\n".join(response_lines)

    await callback.message.answer(response, reply_markup=build_home_keyboard())
    await callback.answer()
