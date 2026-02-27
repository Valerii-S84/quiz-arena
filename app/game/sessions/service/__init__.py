from __future__ import annotations

from app.game.questions.runtime_bank import (
    get_question_by_id,
    get_question_for_mode,
    select_friend_challenge_question,
    select_question_for_mode,
)

from .constants import (
    DAILY_CHALLENGE_TOTAL_QUESTIONS,
    DUEL_ACCEPTED_TTL_SECONDS,
    DUEL_MAX_ACTIVE_PER_USER,
    DUEL_MAX_NEW_PER_DAY,
    DUEL_PENDING_TTL_SECONDS,
    FRIEND_CHALLENGE_FREE_CREATES,
    FRIEND_CHALLENGE_LEVEL_SEQUENCE,
    FRIEND_CHALLENGE_TICKET_PRODUCT_CODE,
    FRIEND_CHALLENGE_TOTAL_ROUNDS,
    FRIEND_CHALLENGE_TTL_SECONDS,
    LEVEL_ORDER,
    PERSISTENT_ADAPTIVE_MODE_BOUNDS,
)
from .friend_challenges_create import create_friend_challenge, create_friend_challenge_rematch
from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _create_friend_challenge_row,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
    _friend_challenge_expires_at,
    _resolve_friend_challenge_access_type,
)
from .friend_challenges_join import join_friend_challenge_by_id, join_friend_challenge_by_token
from .friend_challenges_manage import (
    cancel_friend_challenge_by_creator,
    repost_friend_challenge_as_open,
)
from .friend_challenges_queries import (
    get_friend_challenge_snapshot_for_user,
    get_friend_series_score_for_user,
    list_friend_challenges_for_user,
)
from .friend_challenges_rounds import start_friend_challenge_round
from .friend_challenges_series import (
    create_friend_challenge_best_of_three,
    create_friend_challenge_series_next_game,
)
from .friend_challenges_series_utils import (
    _count_series_wins,
    _resolve_challenge_opponent_user_id,
    _series_wins_needed,
)
from .levels import (
    _clamp_level_for_mode,
    _friend_challenge_level_for_round,
    _is_persistent_adaptive_mode,
    _next_preferred_level,
    _normalize_level,
)
from .question_loading import (
    _build_start_result_from_existing_session,
    _infer_preferred_level_from_recent_attempt,
    _load_question_for_session,
)
from .sessions_daily import abandon_session, get_daily_run_summary
from .sessions_start import get_session_user_id, start_session
from .sessions_submit import submit_answer


class GameSessionService:
    _friend_challenge_expires_at = staticmethod(_friend_challenge_expires_at)
    _expire_friend_challenge_if_due = staticmethod(_expire_friend_challenge_if_due)
    _emit_friend_challenge_expired_event = staticmethod(_emit_friend_challenge_expired_event)
    _resolve_friend_challenge_access_type = staticmethod(_resolve_friend_challenge_access_type)
    _create_friend_challenge_row = staticmethod(_create_friend_challenge_row)
    _build_friend_challenge_snapshot = staticmethod(_build_friend_challenge_snapshot)
    _series_wins_needed = staticmethod(_series_wins_needed)
    _count_series_wins = staticmethod(_count_series_wins)
    _normalize_level = staticmethod(_normalize_level)
    _is_persistent_adaptive_mode = staticmethod(_is_persistent_adaptive_mode)
    _clamp_level_for_mode = staticmethod(_clamp_level_for_mode)
    _next_preferred_level = staticmethod(_next_preferred_level)
    _friend_challenge_level_for_round = staticmethod(_friend_challenge_level_for_round)
    _infer_preferred_level_from_recent_attempt = staticmethod(
        _infer_preferred_level_from_recent_attempt
    )
    _load_question_for_session = staticmethod(_load_question_for_session)
    _build_start_result_from_existing_session = staticmethod(
        _build_start_result_from_existing_session
    )
    _resolve_challenge_opponent_user_id = staticmethod(_resolve_challenge_opponent_user_id)
    create_friend_challenge = staticmethod(create_friend_challenge)
    create_friend_challenge_rematch = staticmethod(create_friend_challenge_rematch)
    create_friend_challenge_best_of_three = staticmethod(create_friend_challenge_best_of_three)
    create_friend_challenge_series_next_game = staticmethod(
        create_friend_challenge_series_next_game
    )
    join_friend_challenge_by_id = staticmethod(join_friend_challenge_by_id)
    join_friend_challenge_by_token = staticmethod(join_friend_challenge_by_token)
    repost_friend_challenge_as_open = staticmethod(repost_friend_challenge_as_open)
    cancel_friend_challenge_by_creator = staticmethod(cancel_friend_challenge_by_creator)
    start_friend_challenge_round = staticmethod(start_friend_challenge_round)
    get_friend_challenge_snapshot_for_user = staticmethod(get_friend_challenge_snapshot_for_user)
    list_friend_challenges_for_user = staticmethod(list_friend_challenges_for_user)
    get_friend_series_score_for_user = staticmethod(get_friend_series_score_for_user)
    start_session = staticmethod(start_session)
    submit_answer = staticmethod(submit_answer)
    abandon_session = staticmethod(abandon_session)
    get_daily_run_summary = staticmethod(get_daily_run_summary)
    get_session_user_id = staticmethod(get_session_user_id)


__all__ = [
    "FRIEND_CHALLENGE_FREE_CREATES",
    "FRIEND_CHALLENGE_LEVEL_SEQUENCE",
    "DAILY_CHALLENGE_TOTAL_QUESTIONS",
    "DUEL_ACCEPTED_TTL_SECONDS",
    "DUEL_MAX_ACTIVE_PER_USER",
    "DUEL_MAX_NEW_PER_DAY",
    "DUEL_PENDING_TTL_SECONDS",
    "FRIEND_CHALLENGE_TICKET_PRODUCT_CODE",
    "FRIEND_CHALLENGE_TOTAL_ROUNDS",
    "FRIEND_CHALLENGE_TTL_SECONDS",
    "LEVEL_ORDER",
    "PERSISTENT_ADAPTIVE_MODE_BOUNDS",
    "GameSessionService",
    "get_question_by_id",
    "get_question_for_mode",
    "select_friend_challenge_question",
    "select_question_for_mode",
]
