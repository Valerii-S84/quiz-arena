from __future__ import annotations

from datetime import datetime, timezone

import structlog
from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.energy_zero_flow import handle_energy_insufficient
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_BOT
from app.game.arena_duels.errors import ArenaDuelError
from app.game.arena_duels.types import ArenaBeatenNotification
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    FriendChallengeAccessError,
)
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
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session, telegram_user=callback.from_user
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
        except EnergyInsufficientError:
            await handle_energy_insufficient(
                callback,
                session=session,
                user_id=snapshot.user_id,
                now_utc=now_utc,
                offer_service=offer_service,
                offer_logging_error=offer_logging_error,
                offer_idempotency_key=f"offer:energy:{callback.id}",
                channel_bonus_service=channel_bonus_service,
            )
            await callback.answer()
            return
        except DailyChallengeAlreadyPlayedError:
            await callback.message.answer(
                TEXTS_DE["msg.daily.challenge.used"], reply_markup=build_home_keyboard()
            )
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
            is_tournament=result.session.source == "TOURNAMENT",
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
            is_tournament=round_start.snapshot.tournament_match_id is not None,
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
    channel_bonus_service,
    build_question_text,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    arena_notification: ArenaBeatenNotification | None = None
    arena_attempt_completed = False
    next_result = None
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session, telegram_user=callback.from_user
        )
        try:
            start_kwargs = {
                "user_id": snapshot.user_id,
                "mode_code": result.mode_code,
                "source": result.source,
                "idempotency_key": f"start:auto:{result.mode_code}:{callback.id}",
                "now_utc": now_utc,
                "preferred_question_level": result.next_preferred_level,
            }
            if result.source == "ARENA_DUEL":
                if result.arena_attempt_id is None or result.arena_answered_round is None:
                    await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
                    return
                next_arena_round = result.arena_answered_round + 1
                if next_arena_round > DUEL_QUESTION_COUNT:
                    completion = await game_session_service.complete_arena_attempt_if_applicable(
                        session,
                        attempt_id=result.arena_attempt_id,
                        user_id=snapshot.user_id,
                        now_utc=now_utc,
                    )
                    if completion is not None:
                        arena_notification = completion.beaten_notification
                    arena_attempt_completed = True
                else:
                    start_kwargs.update(
                        {
                            "arena_attempt_id": result.arena_attempt_id,
                            "arena_round": next_arena_round,
                            "duel_limit_checked": True,
                        }
                    )
            if not arena_attempt_completed:
                next_result = await game_session_service.start_session(session, **start_kwargs)
        except (ArenaDuelError, FriendChallengeAccessError):
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return
        except EnergyInsufficientError:
            await handle_energy_insufficient(
                callback,
                session=session,
                user_id=snapshot.user_id,
                now_utc=now_utc,
                offer_service=offer_service,
                offer_logging_error=offer_logging_error,
                offer_idempotency_key=f"offer:energy:auto:{callback.id}",
                channel_bonus_service=channel_bonus_service,
            )
            await callback.answer()
            return

    if arena_attempt_completed:
        await callback.answer()
        if arena_notification is not None:
            await _send_arena_beaten_notification_best_effort(
                notification=arena_notification,
                happened_at=now_utc,
                bot=callback.bot,
            )
        return
    if next_result is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
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


async def _send_arena_beaten_notification_best_effort(
    *,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    bot,
) -> None:
    try:
        from app.workers.tasks.arena_duels import send_arena_beaten_notification

        await send_arena_beaten_notification(
            notification=notification,
            happened_at=happened_at,
            bot=bot,
            source=EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        logger.warning(
            "arena_beaten_notification_failed",
            arena_duel_id=str(notification.arena_duel_id),
            previous_best_attempt_id=str(notification.previous_best_attempt_id),
            new_best_attempt_id=str(notification.new_best_attempt_id),
            error_type=type(exc).__name__,
        )
