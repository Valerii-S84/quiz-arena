from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.start_flow import _send_home_message
from app.bot.keyboards.daily import build_daily_result_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import DailyChallengeAlreadyPlayedError, SessionNotFoundError
from app.game.sessions.types import AnswerSessionResult, DailyRunSummary


def _build_daily_result_text(*, score: int, total: int, streak: int) -> str:
    if streak > 0:
        return TEXTS_DE["msg.daily.result.summary.with_streak"].format(
            score=score,
            total=total,
            streak=streak,
        )
    return TEXTS_DE["msg.daily.result.summary.no_streak"].format(score=score, total=total)


async def _send_daily_result_message(
    message: Message,
    *,
    summary: DailyRunSummary,
    current_streak: int,
) -> None:
    await message.answer(
        _build_daily_result_text(
            score=summary.score,
            total=summary.total_questions,
            streak=current_streak,
        ),
        reply_markup=build_daily_result_keyboard(daily_run_id=str(summary.daily_run_id)),
    )


async def handle_daily_answer_branch(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    session_local,
    user_onboarding_service,
    game_session_service,
    build_question_text,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if result.idempotent_replay:
        await callback.answer()
        return
    message = cast(Message, callback.message)

    current_question = result.daily_current_question or 1
    total_questions = result.daily_total_questions or 7
    if result.is_correct:
        progress_text = TEXTS_DE["msg.daily.answer.progress.correct"].format(
            current=current_question,
            total=total_questions,
        )
    elif result.correct_answer_text:
        progress_text = TEXTS_DE["msg.daily.answer.progress.incorrect"].format(
            answer=result.correct_answer_text,
            current=current_question,
            total=total_questions,
        )
    else:
        progress_text = TEXTS_DE["msg.daily.answer.progress.incorrect.no_answer"].format(
            current=current_question,
            total=total_questions,
        )
    await message.answer(progress_text)

    if result.daily_completed:
        if result.daily_run_id is None:
            await _send_home_message(message, text=TEXTS_DE["msg.game.daily.finished"])
            await callback.answer()
            return
        await message.answer(
            _build_daily_result_text(
                score=result.daily_score or 0,
                total=total_questions,
                streak=result.current_streak,
            ),
            reply_markup=build_daily_result_keyboard(daily_run_id=str(result.daily_run_id)),
        )
        await callback.answer()
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
                mode_code="DAILY_CHALLENGE",
                source="DAILY_CHALLENGE",
                idempotency_key=f"start:daily:auto:{result.daily_run_id}:{callback.id}",
                now_utc=now_utc,
            )
        except DailyChallengeAlreadyPlayedError:
            if result.daily_run_id is not None:
                summary = await game_session_service.get_daily_run_summary(
                    session,
                    user_id=snapshot.user_id,
                    daily_run_id=result.daily_run_id,
                )
                await _send_daily_result_message(
                    message,
                    summary=summary,
                    current_streak=snapshot.current_streak,
                )
            else:
                await message.answer(
                    TEXTS_DE["msg.daily.challenge.used"],
                    reply_markup=build_home_keyboard(),
                )
            await callback.answer()
            return

    question_text = build_question_text(
        source="DAILY_CHALLENGE",
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=next_result,
    )
    await message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(next_result.session.session_id),
            options=next_result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


async def handle_daily_result_screen(
    callback: CallbackQuery,
    *,
    daily_run_id: UUID,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    message = cast(Message, callback.message)

    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            summary = await game_session_service.get_daily_run_summary(
                session,
                user_id=snapshot.user_id,
                daily_run_id=daily_run_id,
            )
        except SessionNotFoundError:
            await message.answer(
                TEXTS_DE["msg.game.session.not_found"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return

    if summary.status != "COMPLETED":
        await message.answer(
            TEXTS_DE["msg.daily.challenge.used"],
            reply_markup=build_home_keyboard(),
        )
        await callback.answer()
        return

    await _send_daily_result_message(
        message,
        summary=summary,
        current_streak=snapshot.current_streak,
    )
    await callback.answer()
