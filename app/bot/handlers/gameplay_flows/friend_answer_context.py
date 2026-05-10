from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram.types import Message


@dataclass(frozen=True, slots=True)
class FriendAnswerFlowServices:
    session_local: Any
    user_onboarding_service: Any
    game_session_service: Any


@dataclass(frozen=True, slots=True)
class FriendAnswerFlowActions:
    notify_opponent: Callable[..., Awaitable[None]]
    enqueue_friend_challenge_proof_cards: Callable[..., None]
    send_friend_round_question: Callable[..., Awaitable[None]]


@dataclass(frozen=True, slots=True)
class FriendAnswerFlowRendering:
    resolve_opponent_label: Callable[..., Awaitable[str]]
    friend_opponent_user_id: Callable[..., int | None]
    build_friend_score_text: Callable[..., str]
    build_friend_ttl_text: Callable[..., str | None]
    build_friend_finish_text: Callable[..., str]
    build_public_badge_label: Callable[..., str]
    build_friend_proof_card_text: Callable[..., str]
    build_series_progress_text: Callable[..., str]


@dataclass(frozen=True, slots=True)
class FriendAnswerFlowContext:
    services: FriendAnswerFlowServices
    actions: FriendAnswerFlowActions
    rendering: FriendAnswerFlowRendering


@dataclass(frozen=True, slots=True)
class FriendAnswerRequest:
    message: Message


@dataclass(frozen=True, slots=True)
class FriendAnswerProgress:
    snapshot_user_id: int
    challenge: Any
    opponent_label: str
    opponent_user_id: int | None


@dataclass(frozen=True, slots=True)
class StartedFriendRound:
    snapshot: Any
    round_start: Any
