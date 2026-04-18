from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.handlers.start_flow import _send_home_message
from app.bot.keyboards.channel_bonus import build_channel_bonus_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.referral_prompt import build_referral_prompt_keyboard
from app.bot.texts.de import TEXTS_DE
from app.economy.energy.constants import FREE_ENERGY_CAP
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError
from app.game.sessions.types import AnswerSessionResult
from app.services.user_onboarding import HomeSnapshot


@dataclass(slots=True)
class _ParsedAnswerPayload:
    message: Message
    telegram_user: TelegramUser
    session_id: UUID
    selected_option: int


@dataclass(slots=True)
class _PostGamePromptState:
    show_channel_bonus_prompt: bool = False
    show_referral_prompt: bool = False


@dataclass(slots=True)
class _SubmittedAnswerPayload:
    now_utc: datetime
    snapshot: HomeSnapshot
    result: AnswerSessionResult
    post_game_prompt: _PostGamePromptState


@dataclass(slots=True)
class _AnswerFlowDeps:
    session_local: Any
    user_onboarding_service: Any
    referral_service: Any
    channel_bonus_service: Any
    game_session_service: Any
    offer_service: Any
    offer_logging_error: Any
    build_question_text: Any
    emit_analytics_event: Any
    event_source_bot: Any
    continue_regular_mode_after_answer: Any
    handle_daily_answer_branch: Any
    handle_friend_answer_branch: Any
    resolve_opponent_label: Any
    notify_opponent: Any
    friend_opponent_user_id: Any
    build_friend_score_text: Any
    build_friend_ttl_text: Any
    build_friend_finish_text: Any
    build_public_badge_label: Any
    build_friend_proof_card_text: Any
    enqueue_friend_challenge_proof_cards: Any
    build_series_progress_text: Any
    send_friend_round_question: Any


def _build_answer_flow_deps(
    *,
    session_local,
    user_onboarding_service,
    referral_service,
    channel_bonus_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    build_question_text,
    emit_analytics_event,
    event_source_bot,
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
    enqueue_friend_challenge_proof_cards,
    build_series_progress_text,
    send_friend_round_question,
) -> _AnswerFlowDeps:
    return _AnswerFlowDeps(
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        referral_service=referral_service,
        channel_bonus_service=channel_bonus_service,
        game_session_service=game_session_service,
        offer_service=offer_service,
        offer_logging_error=offer_logging_error,
        build_question_text=build_question_text,
        emit_analytics_event=emit_analytics_event,
        event_source_bot=event_source_bot,
        continue_regular_mode_after_answer=continue_regular_mode_after_answer,
        handle_daily_answer_branch=handle_daily_answer_branch,
        handle_friend_answer_branch=handle_friend_answer_branch,
        resolve_opponent_label=resolve_opponent_label,
        notify_opponent=notify_opponent,
        friend_opponent_user_id=friend_opponent_user_id,
        build_friend_score_text=build_friend_score_text,
        build_friend_ttl_text=build_friend_ttl_text,
        build_friend_finish_text=build_friend_finish_text,
        build_public_badge_label=build_public_badge_label,
        build_friend_proof_card_text=build_friend_proof_card_text,
        enqueue_friend_challenge_proof_cards=enqueue_friend_challenge_proof_cards,
        build_series_progress_text=build_series_progress_text,
        send_friend_round_question=send_friend_round_question,
    )


async def _parse_answer_payload(
    callback: CallbackQuery,
    *,
    parse_answer_callback,
) -> _ParsedAnswerPayload | None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    parsed_answer = parse_answer_callback(callback.data)
    if parsed_answer is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    session_id, selected_option = parsed_answer
    return _ParsedAnswerPayload(
        message=cast(Message, callback.message),
        telegram_user=callback.from_user,
        session_id=session_id,
        selected_option=selected_option,
    )


async def _reserve_post_game_prompt(
    *,
    session,
    snapshot: HomeSnapshot,
    result: AnswerSessionResult,
    now_utc: datetime,
    referral_service,
    channel_bonus_service,
    emit_analytics_event,
    event_source_bot,
) -> _PostGamePromptState:
    if result.source not in {"MENU", "DAILY_CHALLENGE"}:
        return _PostGamePromptState()

    show_channel_bonus_prompt = await channel_bonus_service.should_show_post_game_prompt(
        session,
        user_id=snapshot.user_id,
        idempotent_replay=result.idempotent_replay,
    )
    if show_channel_bonus_prompt:
        await emit_analytics_event(
            session,
            event_type="channel_bonus_shown",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"source": "post_game"},
        )
        return _PostGamePromptState(show_channel_bonus_prompt=True)

    show_referral_prompt = await referral_service.reserve_post_game_prompt(
        session,
        user_id=snapshot.user_id,
        now_utc=now_utc,
    )
    if show_referral_prompt:
        await emit_analytics_event(
            session,
            event_type="referral_prompt_shown",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"entrypoint": "post_game"},
        )
    return _PostGamePromptState(show_referral_prompt=show_referral_prompt)


async def _submit_answer(
    callback: CallbackQuery,
    *,
    parsed_answer: _ParsedAnswerPayload,
    deps: _AnswerFlowDeps,
) -> _SubmittedAnswerPayload | None:
    now_utc = datetime.now(timezone.utc)

    async with deps.session_local.begin() as session:
        snapshot = await deps.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=parsed_answer.telegram_user,
        )

        try:
            result = await deps.game_session_service.submit_answer(
                session,
                user_id=snapshot.user_id,
                session_id=parsed_answer.session_id,
                selected_option=parsed_answer.selected_option,
                idempotency_key=f"answer:{callback.id}",
                now_utc=now_utc,
            )
        except SessionNotFoundError:
            await parsed_answer.message.answer(
                TEXTS_DE["msg.game.session.not_found"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return None
        except InvalidAnswerOptionError:
            await parsed_answer.message.answer(TEXTS_DE["msg.system.error"])
            await callback.answer()
            return None

        post_game_prompt = await _reserve_post_game_prompt(
            session=session,
            snapshot=snapshot,
            result=result,
            now_utc=now_utc,
            referral_service=deps.referral_service,
            channel_bonus_service=deps.channel_bonus_service,
            emit_analytics_event=deps.emit_analytics_event,
            event_source_bot=deps.event_source_bot,
        )

    return _SubmittedAnswerPayload(
        now_utc=now_utc,
        snapshot=snapshot,
        result=result,
        post_game_prompt=post_game_prompt,
    )


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
    post_game_prompt: _PostGamePromptState,
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
    parsed_answer: _ParsedAnswerPayload,
    submitted_answer: _SubmittedAnswerPayload,
    deps: _AnswerFlowDeps,
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
        parsed_answer.message,
        post_game_prompt=submitted_answer.post_game_prompt,
        channel_bonus_service=deps.channel_bonus_service,
    )


async def _handle_friend_answer_result(
    callback: CallbackQuery,
    *,
    submitted_answer: _SubmittedAnswerPayload,
    deps: _AnswerFlowDeps,
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
    parsed_answer: _ParsedAnswerPayload,
    submitted_answer: _SubmittedAnswerPayload,
    deps: _AnswerFlowDeps,
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
        parsed_answer.message,
        post_game_prompt=submitted_answer.post_game_prompt,
        channel_bonus_service=deps.channel_bonus_service,
    )


async def _dispatch_submitted_answer(
    callback: CallbackQuery,
    *,
    parsed_answer: _ParsedAnswerPayload,
    submitted_answer: _SubmittedAnswerPayload,
    deps: _AnswerFlowDeps,
) -> None:
    result = submitted_answer.result
    if result.source == "DAILY_CHALLENGE":
        await _handle_daily_answer_result(
            callback,
            parsed_answer=parsed_answer,
            submitted_answer=submitted_answer,
            deps=deps,
        )
        return

    if result.mode_code is None or result.source is None:
        await _send_home_message(parsed_answer.message, text=TEXTS_DE["msg.game.stopped"])
        await callback.answer()
        return

    await parsed_answer.message.answer(_build_answer_feedback_text(result=result))
    if result.source == "FRIEND_CHALLENGE":
        await _handle_friend_answer_result(
            callback,
            submitted_answer=submitted_answer,
            deps=deps,
        )
        return

    await _handle_regular_answer_result(
        callback,
        parsed_answer=parsed_answer,
        submitted_answer=submitted_answer,
        deps=deps,
    )


async def _process_answer_payload(
    callback: CallbackQuery,
    *,
    parsed_answer: _ParsedAnswerPayload,
    deps: _AnswerFlowDeps,
) -> None:
    submitted_answer = await _submit_answer(
        callback,
        parsed_answer=parsed_answer,
        deps=deps,
    )
    if submitted_answer is None:
        return

    await _dispatch_submitted_answer(
        callback,
        parsed_answer=parsed_answer,
        submitted_answer=submitted_answer,
        deps=deps,
    )


async def _run_answer_flow(
    callback: CallbackQuery,
    *,
    parse_answer_callback,
    deps: _AnswerFlowDeps,
) -> None:
    parsed_answer = await _parse_answer_payload(
        callback,
        parse_answer_callback=parse_answer_callback,
    )
    if parsed_answer is None:
        return

    await _process_answer_payload(
        callback,
        parsed_answer=parsed_answer,
        deps=deps,
    )


async def handle_answer(
    callback: CallbackQuery,
    *,
    parse_answer_callback,
    session_local,
    user_onboarding_service,
    referral_service,
    channel_bonus_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    build_question_text,
    emit_analytics_event,
    event_source_bot,
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
    enqueue_friend_challenge_proof_cards,
    build_series_progress_text,
    send_friend_round_question,
) -> None:
    await _run_answer_flow(
        callback,
        parse_answer_callback=parse_answer_callback,
        deps=_build_answer_flow_deps(
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            referral_service=referral_service,
            channel_bonus_service=channel_bonus_service,
            game_session_service=game_session_service,
            offer_service=offer_service,
            offer_logging_error=offer_logging_error,
            build_question_text=build_question_text,
            emit_analytics_event=emit_analytics_event,
            event_source_bot=event_source_bot,
            continue_regular_mode_after_answer=continue_regular_mode_after_answer,
            handle_daily_answer_branch=handle_daily_answer_branch,
            handle_friend_answer_branch=handle_friend_answer_branch,
            resolve_opponent_label=resolve_opponent_label,
            notify_opponent=notify_opponent,
            friend_opponent_user_id=friend_opponent_user_id,
            build_friend_score_text=build_friend_score_text,
            build_friend_ttl_text=build_friend_ttl_text,
            build_friend_finish_text=build_friend_finish_text,
            build_public_badge_label=build_public_badge_label,
            build_friend_proof_card_text=build_friend_proof_card_text,
            enqueue_friend_challenge_proof_cards=enqueue_friend_challenge_proof_cards,
            build_series_progress_text=build_series_progress_text,
            send_friend_round_question=send_friend_round_question,
        ),
    )
