from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.types import StartSessionResult

from .friend_challenges_round_start_drafts import build_friend_challenge_round_start_draft
from .friend_challenges_round_start_headers import apply_friend_challenge_round_header_override
from .question_loading import _build_start_result_from_existing_session
from .sessions_start import start_session


async def build_existing_round_start_result(
    session: AsyncSession,
    *,
    existing_round_session: QuizSession,
    tournament_match_id: UUID | None,
) -> StartSessionResult:
    start_result = await _build_start_result_from_existing_session(
        session,
        existing=existing_round_session,
        idempotent_replay=True,
    )
    await apply_friend_challenge_round_header_override(
        session,
        start_result=start_result,
        tournament_match_id=tournament_match_id,
    )
    return start_result


async def start_new_round_session(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    next_round: int,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
) -> StartSessionResult:
    draft = await build_friend_challenge_round_start_draft(
        session,
        challenge=challenge,
        next_round=next_round,
        now_utc=now_utc,
    )
    start_result = await start_session(
        session,
        user_id=user_id,
        mode_code=challenge.mode_code,
        source="FRIEND_CHALLENGE",
        idempotency_key=idempotency_key,
        now_utc=now_utc,
        selection_seed_override=draft.selection_seed,
        preferred_question_level=draft.preferred_level,
        forced_question_id=draft.forced_question_id,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
        friend_challenge_total_rounds=challenge.total_rounds,
    )
    await apply_friend_challenge_round_header_override(
        session,
        start_result=start_result,
        tournament_match_id=challenge.tournament_match_id,
    )
    return start_result
