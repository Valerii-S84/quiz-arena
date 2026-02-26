from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.start_flow import _send_home_message
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError


async def handle_answer(
    callback: CallbackQuery,
    *,
    parse_answer_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    build_question_text,
    continue_regular_mode_after_answer,
    handle_daily_answer_branch,
    handle_friend_answer_branch,
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
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    message = cast(Message, callback.message)

    parsed_answer = parse_answer_callback(callback.data)
    if parsed_answer is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    session_id, selected_option = parsed_answer
    now_utc = datetime.now(timezone.utc)

    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            result = await game_session_service.submit_answer(
                session,
                user_id=snapshot.user_id,
                session_id=session_id,
                selected_option=selected_option,
                idempotency_key=f"answer:{callback.id}",
                now_utc=now_utc,
            )
        except SessionNotFoundError:
            await callback.message.answer(
                TEXTS_DE["msg.game.session.not_found"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return
        except InvalidAnswerOptionError:
            await callback.message.answer(TEXTS_DE["msg.system.error"])
            await callback.answer()
            return

    answer_key = "msg.game.answer.correct" if result.is_correct else "msg.game.answer.incorrect"
    if result.source == "DAILY_CHALLENGE":
        await handle_daily_answer_branch(
            callback,
            result=result,
            now_utc=now_utc,
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            build_question_text=build_question_text,
        )
        return

    if result.mode_code is None or result.source is None:
        await _send_home_message(message, text=TEXTS_DE["msg.game.stopped"])
        await callback.answer()
        return

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
    await callback.message.answer("\n".join(response_lines))

    if result.source == "FRIEND_CHALLENGE":
        await handle_friend_answer_branch(
            callback,
            result=result,
            now_utc=now_utc,
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            resolve_opponent_label=resolve_opponent_label,
            notify_opponent=notify_opponent,
            friend_opponent_user_id=friend_opponent_user_id,
            build_friend_score_text=build_friend_score_text,
            build_friend_ttl_text=build_friend_ttl_text,
            build_friend_finish_text=build_friend_finish_text,
            build_public_badge_label=build_public_badge_label,
            build_friend_proof_card_text=build_friend_proof_card_text,
            build_series_progress_text=build_series_progress_text,
            send_friend_round_question=send_friend_round_question,
        )
        return

    await continue_regular_mode_after_answer(
        callback,
        result=result,
        now_utc=now_utc,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
        offer_service=offer_service,
        offer_logging_error=offer_logging_error,
        build_question_text=build_question_text,
    )
