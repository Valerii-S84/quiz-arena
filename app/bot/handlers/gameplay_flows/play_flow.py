from __future__ import annotations

from datetime import datetime

import structlog
from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.energy_zero_flow import handle_energy_insufficient
from app.bot.handlers.gameplay_flows.play_flow_context import (
    ContinueModeFlowServices,
    StartModeFlowServices,
)
from app.bot.handlers.gameplay_flows.play_flow_continue import (
    continue_regular_mode_after_answer_impl,
)
from app.bot.handlers.gameplay_flows.play_flow_start import (
    send_friend_round_question_impl,
    start_mode_impl,
)
from app.bot.keyboards.home import build_home_keyboard
from app.game.sessions.types import AnswerSessionResult, FriendChallengeRoundStartResult

logger = structlog.get_logger(__name__)


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
    channel_bonus_service,
    build_question_text,
) -> None:
    services = StartModeFlowServices(
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
        offer_service=offer_service,
        offer_logging_error=offer_logging_error,
        channel_bonus_service=channel_bonus_service,
        build_question_text=build_question_text,
        energy_handler=handle_energy_insufficient,
        home_keyboard_factory=build_home_keyboard,
    )
    await start_mode_impl(
        callback,
        mode_code=mode_code,
        source=source,
        idempotency_key=idempotency_key,
        services=services,
    )


async def send_friend_round_question(
    callback: CallbackQuery,
    *,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    round_start: FriendChallengeRoundStartResult,
    build_question_text,
) -> None:
    await send_friend_round_question_impl(
        callback,
        snapshot_free_energy=snapshot_free_energy,
        snapshot_paid_energy=snapshot_paid_energy,
        round_start=round_start,
        build_question_text=build_question_text,
    )


async def continue_regular_mode_after_answer(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    user_id: int | None = None,
    now_utc: datetime,
    session_local,
    user_onboarding_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    channel_bonus_service,
    build_question_text,
) -> None:
    services = ContinueModeFlowServices(
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
        offer_service=offer_service,
        offer_logging_error=offer_logging_error,
        channel_bonus_service=channel_bonus_service,
        build_question_text=build_question_text,
        energy_handler=handle_energy_insufficient,
        event_logger=logger,
    )
    await continue_regular_mode_after_answer_impl(
        callback,
        result=result,
        user_id=user_id,
        now_utc=now_utc,
        services=services,
    )
