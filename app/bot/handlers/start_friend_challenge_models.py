from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from aiogram.types import InlineKeyboardMarkup

from app.game.sessions.types import FriendChallengeSnapshot


@dataclass(slots=True)
class OutgoingStartMessage:
    text: str
    reply_markup: InlineKeyboardMarkup
    parse_mode: str | None = None
    photo: str | None = None


@dataclass(slots=True)
class StartFriendChallengeHandlingResult:
    handled: bool
    messages: list[OutgoingStartMessage] = field(default_factory=list)
    notify_creator: bool = False
    notify_challenge: FriendChallengeSnapshot | None = None
    notify_joiner_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class StartFriendChallengePayloadContext:
    session: Any
    now_utc: datetime
    snapshot: Any
    friend_invite_token: str | None
    duel_challenge_id: str | None
    start_message_id: int
    game_session_service: Any


@dataclass(frozen=True, slots=True)
class StartFriendChallengeRenderers:
    resolve_opponent_label: Callable[..., Awaitable[str]]
    build_friend_plan_text: Callable[..., str]
    build_friend_score_text: Callable[..., str]
    build_friend_ttl_text: Callable[..., str | None]
    build_question_text: Callable[..., str]
