from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import (
    friend_challenges_round_start_drafts,
    friend_challenges_round_start_question_state,
)
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(**overrides: object) -> FriendChallenge:
    payload: dict[str, object] = {
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 7,
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


@pytest.mark.asyncio
async def test_build_round_start_draft_delegates_to_question_state_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    load_calls: list[dict[str, object]] = []
    question_state = friend_challenges_round_start_question_state.FriendChallengeRoundQuestionState(
        selection_seed=f"friend:{challenge.id}:2:{challenge.mode_code}",
        preferred_level="A2",
        forced_question_id="shared-question",
    )

    async def _fake_load_round_question_state(*_args, **kwargs):
        load_calls.append(kwargs)
        return question_state

    monkeypatch.setattr(
        friend_challenges_round_start_drafts,
        "load_friend_challenge_round_question_state",
        _fake_load_round_question_state,
    )

    draft = await friend_challenges_round_start_drafts.build_friend_challenge_round_start_draft(
        _Session(),
        challenge=challenge,
        next_round=2,
        now_utc=NOW_UTC,
    )

    assert draft == friend_challenges_round_start_drafts.FriendChallengeRoundStartDraft(
        selection_seed=f"friend:{challenge.id}:2:{challenge.mode_code}",
        preferred_level="A2",
        forced_question_id="shared-question",
    )
    assert load_calls == [
        {
            "challenge": challenge,
            "next_round": 2,
            "now_utc": NOW_UTC,
        }
    ]
