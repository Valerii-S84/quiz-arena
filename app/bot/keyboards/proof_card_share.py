from __future__ import annotations

DAILY_CUP_INLINE_SHARE_PREFIX = "proof:daily:"
FRIEND_CHALLENGE_INLINE_SHARE_PREFIX = "proof:duel:"


def build_daily_cup_inline_share_query(*, tournament_id: str) -> str:
    return f"{DAILY_CUP_INLINE_SHARE_PREFIX}{tournament_id}"


def build_friend_challenge_inline_share_query(*, challenge_id: str) -> str:
    return f"{FRIEND_CHALLENGE_INLINE_SHARE_PREFIX}{challenge_id}"
