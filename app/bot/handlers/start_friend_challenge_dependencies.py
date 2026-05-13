from __future__ import annotations

from datetime import datetime

from app.bot.handlers.start_helpers import _resolve_opponent_label
from app.bot.handlers.start_views import (
    _build_friend_plan_text,
    _build_friend_score_text,
    _build_friend_ttl_text,
    _build_question_text,
)
from app.game.sessions.service import GameSessionService

from .start_friend_challenge_models import (
    StartFriendChallengePayloadContext,
    StartFriendChallengeRenderers,
)

FRIEND_CHALLENGE_RENDERERS = StartFriendChallengeRenderers(
    resolve_opponent_label=_resolve_opponent_label,
    build_friend_plan_text=_build_friend_plan_text,
    build_friend_score_text=_build_friend_score_text,
    build_friend_ttl_text=_build_friend_ttl_text,
    build_question_text=_build_question_text,
)


def build_friend_challenge_payload_context(
    *,
    session,
    now_utc: datetime,
    snapshot,
    friend_invite_token: str | None,
    duel_challenge_id: str | None,
    start_message_id: int,
) -> StartFriendChallengePayloadContext:
    return StartFriendChallengePayloadContext(
        session=session,
        now_utc=now_utc,
        snapshot=snapshot,
        friend_invite_token=friend_invite_token,
        duel_challenge_id=duel_challenge_id,
        start_message_id=start_message_id,
        game_session_service=GameSessionService,
    )
