from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from app.workers.tasks.tournaments_messaging_text import resolve_match_context


def test_resolve_match_context_returns_playable_self_bot_challenge() -> None:
    challenge_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    play_challenge_id, opponent_user_id = resolve_match_context(
        round_matches=[
            SimpleNamespace(
                user_a=101,
                user_b=None,
                status="PENDING",
                friend_challenge_id=challenge_id,
            )
        ],
        viewer_user_id=101,
    )

    assert play_challenge_id == str(challenge_id)
    assert opponent_user_id is None
