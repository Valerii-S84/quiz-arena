from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any

from aiogram.types import Message

from app.bot.handlers import (
    gameplay_analytics,
    gameplay_callbacks,
    gameplay_helpers,
    gameplay_proof_cards,
    gameplay_views,
)
from app.bot.handlers.gameplay_flows import daily_flow, friend_answer_flow, play_flow
from app.bot.handlers.gameplay_flows.friend_answer_context import (
    FriendAnswerFlowActions,
    FriendAnswerFlowContext,
    FriendAnswerFlowRendering,
    FriendAnswerFlowServices,
)
from app.db.session import SessionLocal
from app.economy.offers.service import OfferLoggingError, OfferService
from app.economy.referrals.service import ReferralService
from app.game.sessions.service import GameSessionService
from app.services.channel_bonus import ChannelBonusService
from app.services.user_onboarding import UserOnboardingService

EVENT_SOURCE_BOT = "BOT"


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


def build_answer_flow_context() -> AnswerFlowContext:
    resolve_opponent_label = partial(
        gameplay_helpers._resolve_opponent_label,
        session_local=SessionLocal,
        users_repo=UserOnboardingService,
        format_user_label=gameplay_views._format_user_label,
    )
    notify_opponent = partial(
        gameplay_helpers._notify_opponent,
        session_local=SessionLocal,
        users_repo=UserOnboardingService,
    )
    send_friend_round_question = partial(
        play_flow.send_friend_round_question,
        build_question_text=gameplay_views._build_question_text,
    )
    return AnswerFlowContext(
        parse_answer_callback=gameplay_callbacks.parse_answer_callback,
        services=AnswerFlowServices(
            session_local=SessionLocal,
            user_onboarding_service=UserOnboardingService,
            referral_service=ReferralService,
            channel_bonus_service=ChannelBonusService,
            game_session_service=GameSessionService,
            offer_service=OfferService,
            offer_logging_error=OfferLoggingError,
        ),
        analytics=AnswerFlowAnalytics(
            emit_event=gameplay_analytics.emit_analytics_event,
            event_source_bot=EVENT_SOURCE_BOT,
        ),
        branches=AnswerFlowBranches(
            continue_regular_mode_after_answer=play_flow.continue_regular_mode_after_answer,
            handle_daily_answer_branch=daily_flow.handle_daily_answer_branch,
            handle_friend_answer_branch=friend_answer_flow.handle_friend_answer_branch,
            notify_opponent=notify_opponent,
            enqueue_friend_challenge_proof_cards=gameplay_proof_cards.enqueue_duel_proof_cards,
            send_friend_round_question=send_friend_round_question,
        ),
        rendering=AnswerFlowRendering(
            build_question_text=gameplay_views._build_question_text,
            resolve_opponent_label=resolve_opponent_label,
            friend_opponent_user_id=gameplay_helpers._friend_opponent_user_id,
            build_friend_score_text=gameplay_views._build_friend_score_text,
            build_friend_ttl_text=gameplay_views._build_friend_ttl_text,
            build_friend_finish_text=gameplay_views._build_friend_finish_text,
            build_public_badge_label=gameplay_views._build_public_badge_label,
            build_friend_proof_card_text=gameplay_views._build_friend_proof_card_text,
            build_series_progress_text=gameplay_views._build_series_progress_text,
        ),
    )


def build_friend_answer_flow_context(context: AnswerFlowContext) -> FriendAnswerFlowContext:
    return FriendAnswerFlowContext(
        services=FriendAnswerFlowServices(
            session_local=context.services.session_local,
            user_onboarding_service=context.services.user_onboarding_service,
            game_session_service=context.services.game_session_service,
        ),
        actions=FriendAnswerFlowActions(
            notify_opponent=context.branches.notify_opponent,
            enqueue_friend_challenge_proof_cards=(
                context.branches.enqueue_friend_challenge_proof_cards
            ),
            send_friend_round_question=context.branches.send_friend_round_question,
        ),
        rendering=FriendAnswerFlowRendering(
            resolve_opponent_label=context.rendering.resolve_opponent_label,
            friend_opponent_user_id=context.rendering.friend_opponent_user_id,
            build_friend_score_text=context.rendering.build_friend_score_text,
            build_friend_ttl_text=context.rendering.build_friend_ttl_text,
            build_friend_finish_text=context.rendering.build_friend_finish_text,
            build_public_badge_label=context.rendering.build_public_badge_label,
            build_friend_proof_card_text=context.rendering.build_friend_proof_card_text,
            build_series_progress_text=context.rendering.build_series_progress_text,
        ),
    )
