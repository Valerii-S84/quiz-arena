from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.start_flow import _send_home_message
from app.bot.keyboards.channel_bonus import build_channel_bonus_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.referral_prompt import build_referral_prompt_keyboard
from app.bot.texts.de import TEXTS_DE
from app.economy.energy.constants import FREE_ENERGY_CAP
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError
from app.game.sessions.types import AnswerSessionResult


@dataclass(frozen=True, slots=True)
class AnswerFlowServices:
    session_local: Any
    user_onboarding_service: Any
    referral_service: Any
    channel_bonus_service: Any
    game_session_service: Any
    offer_service: Any
    offer_logging_error: type[Exception]


@dataclass(frozen=True, slots=True)
class AnswerFlowAnalytics:
    emit_event: Callable[..., Awaitable[None]]
    event_source_bot: str


@dataclass(frozen=True, slots=True)
class AnswerFlowBranches:
    continue_regular_mode_after_answer: Callable[..., Awaitable[None]]
    handle_daily_answer_branch: Callable[..., Awaitable[None]]
    handle_friend_answer_branch: Callable[..., Awaitable[None]]
    notify_opponent: Callable[..., Awaitable[None]]
    enqueue_friend_challenge_proof_cards: Callable[..., None]
    send_friend_round_question: Callable[..., Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AnswerFlowRendering:
    build_question_text: Callable[..., str]
    resolve_opponent_label: Callable[..., Awaitable[str]]
    friend_opponent_user_id: Callable[..., int | None]
    build_friend_score_text: Callable[..., str]
    build_friend_ttl_text: Callable[..., str | None]
    build_friend_finish_text: Callable[..., str]
    build_public_badge_label: Callable[..., str]
    build_friend_proof_card_text: Callable[..., str]
    build_series_progress_text: Callable[..., str]


@dataclass(frozen=True, slots=True)
class AnswerFlowContext:
    parse_answer_callback: Callable[[str], tuple[Any, int] | None]
    services: AnswerFlowServices
    analytics: AnswerFlowAnalytics
    branches: AnswerFlowBranches
    rendering: AnswerFlowRendering


@dataclass(frozen=True, slots=True)
class AnswerRequest:
    message: Message
    session_id: Any
    selected_option: int
    now_utc: datetime


@dataclass(frozen=True, slots=True)
class PostGamePromptState:
    show_channel_bonus: bool = False
    show_referral: bool = False


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

    submitted = await _record_answer_and_prompts(callback, request=request, context=context)
    if submitted is None:
        return

    result = submitted.result
    if result.source == "DAILY_CHALLENGE":
        await _continue_daily_answer(
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

    await _send_answer_feedback(request.message, result=result)

    if result.source == "FRIEND_CHALLENGE":
        await _continue_friend_answer(callback, result=result, request=request, context=context)
        return

    await _continue_regular_answer(
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

        prompts = await _resolve_post_game_prompts(
            session,
            user_id=snapshot.user_id,
            result=result,
            request=request,
            context=context,
        )
    return SubmittedAnswerState(result=result, prompts=prompts)


async def _resolve_post_game_prompts(
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


async def _send_answer_feedback(
    message: Message,
    *,
    result: AnswerSessionResult,
) -> None:
    response_lines = _build_answer_feedback_lines(result)
    await message.answer("\n".join(response_lines))


def _build_answer_feedback_lines(result: AnswerSessionResult) -> list[str]:
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


async def _continue_daily_answer(
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
    await _send_post_game_prompt(request.message, prompts=prompts, context=context)


async def _continue_friend_answer(
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
        session_local=context.services.session_local,
        user_onboarding_service=context.services.user_onboarding_service,
        game_session_service=context.services.game_session_service,
        resolve_opponent_label=context.rendering.resolve_opponent_label,
        notify_opponent=context.branches.notify_opponent,
        friend_opponent_user_id=context.rendering.friend_opponent_user_id,
        build_friend_score_text=context.rendering.build_friend_score_text,
        build_friend_ttl_text=context.rendering.build_friend_ttl_text,
        build_friend_finish_text=context.rendering.build_friend_finish_text,
        build_public_badge_label=context.rendering.build_public_badge_label,
        build_friend_proof_card_text=context.rendering.build_friend_proof_card_text,
        enqueue_friend_challenge_proof_cards=context.branches.enqueue_friend_challenge_proof_cards,
        build_series_progress_text=context.rendering.build_series_progress_text,
        send_friend_round_question=context.branches.send_friend_round_question,
    )


async def _continue_regular_answer(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    request: AnswerRequest,
    prompts: PostGamePromptState,
    context: AnswerFlowContext,
) -> None:
    await context.branches.continue_regular_mode_after_answer(
        callback,
        result=result,
        now_utc=request.now_utc,
        session_local=context.services.session_local,
        user_onboarding_service=context.services.user_onboarding_service,
        game_session_service=context.services.game_session_service,
        offer_service=context.services.offer_service,
        offer_logging_error=context.services.offer_logging_error,
        channel_bonus_service=context.services.channel_bonus_service,
        build_question_text=context.rendering.build_question_text,
    )
    await _send_post_game_prompt(request.message, prompts=prompts, context=context)


async def _send_post_game_prompt(
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
