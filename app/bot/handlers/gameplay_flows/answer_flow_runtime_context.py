from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult
from app.services.user_onboarding import HomeSnapshot


@dataclass(slots=True)
class ParsedAnswerPayload:
    message: Message
    telegram_user: TelegramUser
    session_id: UUID
    selected_option: int


@dataclass(slots=True)
class PostGamePromptState:
    show_channel_bonus_prompt: bool = False
    show_referral_prompt: bool = False


@dataclass(slots=True)
class SubmittedAnswerPayload:
    now_utc: datetime
    snapshot: HomeSnapshot
    result: AnswerSessionResult
    post_game_prompt: PostGamePromptState


@dataclass(slots=True)
class AnswerFlowDeps:
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


def build_answer_flow_deps(
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
) -> AnswerFlowDeps:
    return AnswerFlowDeps(
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


async def parse_answer_payload(
    callback: CallbackQuery,
    *,
    parse_answer_callback,
) -> ParsedAnswerPayload | None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    parsed_answer = parse_answer_callback(callback.data)
    if parsed_answer is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    session_id, selected_option = parsed_answer
    return ParsedAnswerPayload(
        message=cast(Message, callback.message),
        telegram_user=callback.from_user,
        session_id=session_id,
        selected_option=selected_option,
    )
