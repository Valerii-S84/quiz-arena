from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.answer_context import (
    AnswerFlowContext,
    AnswerRequest,
    PostGamePromptState,
    build_friend_answer_flow_context,
)
from app.bot.handlers.gameplay_flows.answer_delivery import send_post_game_prompt
from app.game.sessions.types import AnswerSessionResult


async def continue_daily_answer(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    request: AnswerRequest,
    prompts: PostGamePromptState,
    context: AnswerFlowContext,
) -> None:
    await context.branches.handle_daily_answer_branch(
        callback,
        result=result,
        now_utc=request.now_utc,
        session_local=context.services.session_local,
        user_onboarding_service=context.services.user_onboarding_service,
        game_session_service=context.services.game_session_service,
        build_question_text=context.rendering.build_question_text,
    )
    await send_post_game_prompt(request.message, prompts=prompts, context=context)


async def continue_friend_answer(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    request: AnswerRequest,
    context: AnswerFlowContext,
) -> None:
    await context.branches.handle_friend_answer_branch(
        callback,
        result=result,
        now_utc=request.now_utc,
        context=build_friend_answer_flow_context(context),
    )


async def continue_regular_answer(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    request: AnswerRequest,
    prompts: PostGamePromptState,
    user_id: int,
    context: AnswerFlowContext,
) -> None:
    await context.branches.continue_regular_mode_after_answer(
        callback,
        result=result,
        user_id=user_id,
        now_utc=request.now_utc,
        session_local=context.services.session_local,
        user_onboarding_service=context.services.user_onboarding_service,
        game_session_service=context.services.game_session_service,
        offer_service=context.services.offer_service,
        offer_logging_error=context.services.offer_logging_error,
        channel_bonus_service=context.services.channel_bonus_service,
        build_question_text=context.rendering.build_question_text,
    )
    await send_post_game_prompt(request.message, prompts=prompts, context=context)
