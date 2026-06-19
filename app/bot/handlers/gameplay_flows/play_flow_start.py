from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.play_flow_context import (
    BuildQuestionText,
    StartModeFlowServices,
)
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.modes.rules import is_zero_cost_source
from app.game.sessions.errors import DailyChallengeAlreadyPlayedError, EnergyInsufficientError
from app.game.sessions.types import FriendChallengeRoundStartResult


@dataclass(frozen=True, slots=True)
class _StartUserSnapshot:
    user_id: int
    free_energy: int = 0
    paid_energy: int = 0


async def start_mode_impl(
    callback: CallbackQuery,
    *,
    mode_code: str,
    source: str,
    idempotency_key: str,
    services: StartModeFlowServices,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with services.session_local.begin() as session:
        snapshot = await _resolve_start_user_snapshot(
            session,
            telegram_user=callback.from_user,
            source=source,
            now_utc=now_utc,
            services=services,
        )
        try:
            result = await services.game_session_service.start_session(
                session,
                user_id=snapshot.user_id,
                mode_code=mode_code,
                source=source,
                idempotency_key=idempotency_key,
                now_utc=now_utc,
            )
        except EnergyInsufficientError:
            await services.energy_handler(
                callback,
                session=session,
                user_id=snapshot.user_id,
                now_utc=now_utc,
                offer_service=services.offer_service,
                offer_logging_error=services.offer_logging_error,
                offer_idempotency_key=f"offer:energy:{callback.id}",
                channel_bonus_service=services.channel_bonus_service,
            )
            await callback.answer()
            return
        except DailyChallengeAlreadyPlayedError:
            await callback.message.answer(
                TEXTS_DE["msg.daily.challenge.used"],
                reply_markup=services.home_keyboard_factory(),
            )
            await callback.answer()
            return

    await _send_started_question(
        callback,
        source=source,
        snapshot=snapshot,
        start_result=result,
        build_question_text=services.build_question_text,
    )
    await callback.answer()


async def _resolve_start_user_snapshot(
    session,
    *,
    telegram_user,
    source: str,
    now_utc: datetime,
    services: StartModeFlowServices,
):
    if is_zero_cost_source(source):
        return await services.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )

    get_existing_user_id = getattr(
        services.user_onboarding_service,
        "get_existing_user_id_by_telegram_user_id",
        None,
    )
    if get_existing_user_id is not None:
        user_id = await get_existing_user_id(session, telegram_user.id)
        if user_id is not None:
            return _StartUserSnapshot(user_id=int(user_id))

    touch_existing_user = getattr(services.user_onboarding_service, "touch_existing_user", None)
    if touch_existing_user is not None:
        user = await touch_existing_user(
            session,
            telegram_user=telegram_user,
            now_utc=now_utc,
        )
        if user is not None:
            return _StartUserSnapshot(user_id=int(user.id))

    return await services.user_onboarding_service.ensure_home_snapshot(
        session,
        telegram_user=telegram_user,
    )


async def send_friend_round_question_impl(
    callback: CallbackQuery,
    *,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    round_start: FriendChallengeRoundStartResult,
    build_question_text: BuildQuestionText,
) -> None:
    if callback.message is None or round_start.start_result is None:
        return

    question_text = build_question_text(
        source="FRIEND_CHALLENGE",
        snapshot_free_energy=snapshot_free_energy,
        snapshot_paid_energy=snapshot_paid_energy,
        start_result=round_start.start_result,
    )
    await _send_question_message(
        callback,
        question_text=question_text,
        session_id=str(round_start.start_result.session.session_id),
        options=round_start.start_result.session.options,
        is_tournament=round_start.snapshot.tournament_match_id is not None,
    )


async def _send_started_question(
    callback: CallbackQuery,
    *,
    source: str,
    snapshot,
    start_result,
    build_question_text: BuildQuestionText,
) -> None:
    question_text = build_question_text(
        source=source,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=start_result,
    )
    await _send_question_message(
        callback,
        question_text=question_text,
        session_id=str(start_result.session.session_id),
        options=start_result.session.options,
        is_tournament=start_result.session.source == "TOURNAMENT",
    )


async def _send_question_message(
    callback: CallbackQuery,
    *,
    question_text: str,
    session_id: str,
    options,
    is_tournament: bool,
) -> None:
    if callback.message is None:
        return

    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=session_id,
            options=options,
            is_tournament=is_tournament,
        ),
        parse_mode="HTML",
    )
