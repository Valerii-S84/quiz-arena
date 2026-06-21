from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.gameplay_flows import answer_branches
from app.bot.handlers.gameplay_flows.answer_context import (
    AnswerFlowContext,
    AnswerRequest,
    PostGamePromptState,
)
from app.bot.handlers.gameplay_flows.answer_delivery import (
    resolve_post_game_prompts,
    send_answer_feedback,
)
from app.bot.handlers.start_flow import _send_home_message
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.entitlements_repo import entitlement_request_cache
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError
from app.game.sessions.types import AnswerSessionResult


@dataclass(frozen=True, slots=True)
class SubmittedAnswerState:
    result: AnswerSessionResult
    prompts: PostGamePromptState


async def handle_answer(
    callback: CallbackQuery,
    *,
    context: AnswerFlowContext,
) -> None:
    request = await _parse_answer_request(callback, context=context)
    if request is None:
        return

    with entitlement_request_cache():
        submitted = await _record_answer_and_prompts(callback, request=request, context=context)
        if submitted is None:
            return

        result = submitted.result
        if result.source == "DAILY_CHALLENGE":
            await answer_branches.continue_daily_answer(
                callback,
                result=result,
                request=request,
                prompts=submitted.prompts,
                context=context,
            )
            return

        if result.mode_code is None or result.source is None:
            await _send_home_message(request.message, text=TEXTS_DE["msg.game.stopped"])
            await callback.answer()
            return

        await send_answer_feedback(request.message, result=result)

        if result.source == "FRIEND_CHALLENGE":
            await answer_branches.continue_friend_answer(
                callback,
                result=result,
                request=request,
                context=context,
            )
            return

        await answer_branches.continue_regular_answer(
            callback,
            result=result,
            request=request,
            prompts=submitted.prompts,
            context=context,
        )


async def _parse_answer_request(
    callback: CallbackQuery,
    *,
    context: AnswerFlowContext,
) -> AnswerRequest | None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None
    message = cast(Message, callback.message)

    parsed_answer = context.parse_answer_callback(callback.data)
    if parsed_answer is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    session_id, selected_option = parsed_answer
    return AnswerRequest(
        message=message,
        session_id=session_id,
        selected_option=selected_option,
        now_utc=datetime.now(timezone.utc),
    )


async def _record_answer_and_prompts(
    callback: CallbackQuery,
    *,
    request: AnswerRequest,
    context: AnswerFlowContext,
) -> SubmittedAnswerState | None:
    services = context.services
    async with services.session_local.begin() as session:
        snapshot = await services.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            result = await services.game_session_service.submit_answer(
                session,
                user_id=snapshot.user_id,
                session_id=request.session_id,
                selected_option=request.selected_option,
                idempotency_key=f"answer:{callback.id}",
                now_utc=request.now_utc,
            )
        except SessionNotFoundError:
            await request.message.answer(
                TEXTS_DE["msg.game.session.not_found"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return None
        except InvalidAnswerOptionError:
            await request.message.answer(TEXTS_DE["msg.system.error"])
            await callback.answer()
            return None

        prompts = await resolve_post_game_prompts(
            session,
            user_id=snapshot.user_id,
            result=result,
            request=request,
            context=context,
        )
    return SubmittedAnswerState(result=result, prompts=prompts)
