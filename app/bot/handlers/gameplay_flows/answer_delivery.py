from __future__ import annotations

from typing import Any

from aiogram.types import Message

from app.bot.handlers.gameplay_flows.answer_context import (
    AnswerFlowContext,
    AnswerRequest,
    PostGamePromptState,
)
from app.bot.keyboards.channel_bonus import build_channel_bonus_keyboard
from app.bot.keyboards.referral_prompt import build_referral_prompt_keyboard
from app.bot.texts.de import TEXTS_DE
from app.economy.energy.constants import FREE_ENERGY_CAP
from app.game.sessions.types import AnswerSessionResult


async def resolve_post_game_prompts(
    session: Any,
    *,
    user_id: int,
    result: AnswerSessionResult,
    request: AnswerRequest,
    context: AnswerFlowContext,
) -> PostGamePromptState:
    if result.source not in {"MENU", "DAILY_CHALLENGE"}:
        return PostGamePromptState()

    services = context.services
    show_channel_bonus = await services.channel_bonus_service.should_show_post_game_prompt(
        session,
        user_id=user_id,
        idempotent_replay=result.idempotent_replay,
    )
    if show_channel_bonus:
        await context.analytics.emit_event(
            session,
            event_type="channel_bonus_shown",
            source=context.analytics.event_source_bot,
            happened_at=request.now_utc,
            user_id=user_id,
            payload={"source": "post_game"},
        )
        return PostGamePromptState(show_channel_bonus=True)

    show_referral = await services.referral_service.reserve_post_game_prompt(
        session,
        user_id=user_id,
        now_utc=request.now_utc,
    )
    if show_referral:
        await context.analytics.emit_event(
            session,
            event_type="referral_prompt_shown",
            source=context.analytics.event_source_bot,
            happened_at=request.now_utc,
            user_id=user_id,
            payload={"entrypoint": "post_game"},
        )
    return PostGamePromptState(show_referral=show_referral)


async def send_answer_feedback(message: Message, *, result: AnswerSessionResult) -> None:
    await message.answer("\n".join(build_answer_feedback_lines(result)))


def build_answer_feedback_lines(result: AnswerSessionResult) -> list[str]:
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
    return response_lines


async def send_post_game_prompt(
    message: Message,
    *,
    prompts: PostGamePromptState,
    context: AnswerFlowContext,
) -> None:
    if prompts.show_channel_bonus:
        await message.answer(
            TEXTS_DE["msg.channel.bonus.offer"].format(max_energy=FREE_ENERGY_CAP),
            reply_markup=build_channel_bonus_keyboard(
                channel_url=context.services.channel_bonus_service.resolve_channel_url()
            ),
        )
    elif prompts.show_referral:
        await message.answer(
            TEXTS_DE["msg.referral.prompt.after_game"],
            reply_markup=build_referral_prompt_keyboard(),
        )
