from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.gameplay_flows.answer_flow_delivery_context import (
    AnswerFlowDeliveryDeps,
    PostGamePromptLike,
    SubmittedAnswerLike,
)
from app.bot.keyboards.channel_bonus import build_channel_bonus_keyboard
from app.bot.keyboards.referral_prompt import build_referral_prompt_keyboard
from app.bot.texts.de import TEXTS_DE
from app.economy.energy.constants import FREE_ENERGY_CAP
from app.game.sessions.types import AnswerSessionResult


def _build_answer_feedback_text(*, result: AnswerSessionResult) -> str:
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
    return "\n".join(response_lines)


async def _send_post_game_prompt(
    message: Message,
    *,
    post_game_prompt: PostGamePromptLike,
    channel_bonus_service,
) -> None:
    if post_game_prompt.show_channel_bonus_prompt:
        await message.answer(
            TEXTS_DE["msg.channel.bonus.offer"].format(max_energy=FREE_ENERGY_CAP),
            reply_markup=build_channel_bonus_keyboard(
                channel_url=channel_bonus_service.resolve_channel_url()
            ),
        )
        return

    if post_game_prompt.show_referral_prompt:
        await message.answer(
            TEXTS_DE["msg.referral.prompt.after_game"],
            reply_markup=build_referral_prompt_keyboard(),
        )


async def _handle_daily_answer_result(
    callback: CallbackQuery,
    *,
    message: Message,
    submitted_answer: SubmittedAnswerLike,
    deps: AnswerFlowDeliveryDeps,
) -> None:
    await deps.handle_daily_answer_branch(
        callback,
        result=submitted_answer.result,
        now_utc=submitted_answer.now_utc,
        session_local=deps.session_local,
        user_onboarding_service=deps.user_onboarding_service,
        game_session_service=deps.game_session_service,
        build_question_text=deps.build_question_text,
    )
    await _send_post_game_prompt(
        message,
        post_game_prompt=submitted_answer.post_game_prompt,
        channel_bonus_service=deps.channel_bonus_service,
    )


async def _handle_friend_answer_result(
    callback: CallbackQuery,
    *,
    submitted_answer: SubmittedAnswerLike,
    deps: AnswerFlowDeliveryDeps,
) -> None:
    await deps.handle_friend_answer_branch(
        callback,
        result=submitted_answer.result,
        now_utc=submitted_answer.now_utc,
        session_local=deps.session_local,
        user_onboarding_service=deps.user_onboarding_service,
        game_session_service=deps.game_session_service,
        resolve_opponent_label=deps.resolve_opponent_label,
        notify_opponent=deps.notify_opponent,
        friend_opponent_user_id=deps.friend_opponent_user_id,
        build_friend_score_text=deps.build_friend_score_text,
        build_friend_ttl_text=deps.build_friend_ttl_text,
        build_friend_finish_text=deps.build_friend_finish_text,
        build_public_badge_label=deps.build_public_badge_label,
        build_friend_proof_card_text=deps.build_friend_proof_card_text,
        enqueue_friend_challenge_proof_cards=deps.enqueue_friend_challenge_proof_cards,
        build_series_progress_text=deps.build_series_progress_text,
        send_friend_round_question=deps.send_friend_round_question,
    )


async def _handle_regular_answer_result(
    callback: CallbackQuery,
    *,
    message: Message,
    submitted_answer: SubmittedAnswerLike,
    deps: AnswerFlowDeliveryDeps,
) -> None:
    await deps.continue_regular_mode_after_answer(
        callback,
        result=submitted_answer.result,
        now_utc=submitted_answer.now_utc,
        session_local=deps.session_local,
        user_onboarding_service=deps.user_onboarding_service,
        game_session_service=deps.game_session_service,
        offer_service=deps.offer_service,
        offer_logging_error=deps.offer_logging_error,
        channel_bonus_service=deps.channel_bonus_service,
        build_question_text=deps.build_question_text,
    )
    await _send_post_game_prompt(
        message,
        post_game_prompt=submitted_answer.post_game_prompt,
        channel_bonus_service=deps.channel_bonus_service,
    )


async def dispatch_submitted_answer(
    callback: CallbackQuery,
    *,
    message: Message,
    submitted_answer: SubmittedAnswerLike,
    deps: AnswerFlowDeliveryDeps,
    send_home_message,
) -> None:
    result = submitted_answer.result
    if result.source == "DAILY_CHALLENGE":
        await _handle_daily_answer_result(
            callback,
            message=message,
            submitted_answer=submitted_answer,
            deps=deps,
        )
        return

    if result.mode_code is None or result.source is None:
        await send_home_message(message, text=TEXTS_DE["msg.game.stopped"])
        await callback.answer()
        return

    await message.answer(_build_answer_feedback_text(result=result))
    if result.source == "FRIEND_CHALLENGE":
        await _handle_friend_answer_result(
            callback,
            submitted_answer=submitted_answer,
            deps=deps,
        )
        return

    await _handle_regular_answer_result(
        callback,
        message=message,
        submitted_answer=submitted_answer,
        deps=deps,
    )
