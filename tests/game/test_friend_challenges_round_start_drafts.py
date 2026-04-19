from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import friend_challenges_round_start_drafts
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _challenge(**overrides: object) -> FriendChallenge:
    payload: dict[str, object] = {
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 7,
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


@pytest.mark.asyncio
async def test_build_round_start_draft_reuses_shared_round_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    monkeypatch.setattr(
        friend_challenges_round_start_drafts,
        "_friend_challenge_level_for_round",
        lambda **_kwargs: "A2",
    )
    monkeypatch.setattr(
        friend_challenges_round_start_drafts.QuizSessionsRepo,
        "get_by_friend_challenge_round_any_user",
        _async_return(SimpleNamespace(question_id="shared-question")),
    )

    async def _unexpected_list_previous_round_ids(*args, **kwargs):
        del args, kwargs
        pytest.fail("history lookup should not run when a shared round session already exists")

    monkeypatch.setattr(
        friend_challenges_round_start_drafts.QuizSessionsRepo,
        "list_friend_challenge_question_ids_before_round",
        _unexpected_list_previous_round_ids,
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


@pytest.mark.asyncio
async def test_build_round_start_draft_uses_planned_question_ids_before_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(question_ids=["q-1", "q-2", "q-3"])
    monkeypatch.setattr(
        friend_challenges_round_start_drafts,
        "_friend_challenge_level_for_round",
        lambda **_kwargs: "B1",
    )
    monkeypatch.setattr(
        friend_challenges_round_start_drafts.QuizSessionsRepo,
        "get_by_friend_challenge_round_any_user",
        _async_return(None),
    )

    async def _unexpected_list_previous_round_ids(*args, **kwargs):
        del args, kwargs
        pytest.fail("history lookup should not run when a planned question id is available")

    monkeypatch.setattr(
        friend_challenges_round_start_drafts.QuizSessionsRepo,
        "list_friend_challenge_question_ids_before_round",
        _unexpected_list_previous_round_ids,
    )

    draft = await friend_challenges_round_start_drafts.build_friend_challenge_round_start_draft(
        _Session(),
        challenge=challenge,
        next_round=2,
        now_utc=NOW_UTC,
    )

    assert draft == friend_challenges_round_start_drafts.FriendChallengeRoundStartDraft(
        selection_seed=f"friend:{challenge.id}:2:{challenge.mode_code}",
        preferred_level="B1",
        forced_question_id="q-2",
    )


@pytest.mark.asyncio
async def test_build_round_start_draft_selects_question_from_history_when_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(question_ids=None)
    captured: dict[str, object] = {}

    async def _fake_select_friend_challenge_question(*args, **kwargs):
        del args
        captured["kwargs"] = kwargs
        return SimpleNamespace(question_id="selected-question")

    monkeypatch.setattr(
        friend_challenges_round_start_drafts,
        "_friend_challenge_level_for_round",
        lambda **_kwargs: "A1",
    )
    monkeypatch.setattr(
        friend_challenges_round_start_drafts.QuizSessionsRepo,
        "get_by_friend_challenge_round_any_user",
        _async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_round_start_drafts.QuizSessionsRepo,
        "list_friend_challenge_question_ids_before_round",
        _async_return(["prev-1", "prev-2"]),
    )
    monkeypatch.setattr(
        "app.game.sessions.service.select_friend_challenge_question",
        _fake_select_friend_challenge_question,
    )

    draft = await friend_challenges_round_start_drafts.build_friend_challenge_round_start_draft(
        _Session(),
        challenge=challenge,
        next_round=3,
        now_utc=NOW_UTC,
    )

    assert draft == friend_challenges_round_start_drafts.FriendChallengeRoundStartDraft(
        selection_seed=f"friend:{challenge.id}:3:{challenge.mode_code}",
        preferred_level="A1",
        forced_question_id="selected-question",
    )
    assert captured["kwargs"] == {
        "local_date_berlin": NOW_UTC.date(),
        "previous_round_question_ids": ["prev-1", "prev-2"],
        "selection_seed": f"friend:{challenge.id}:3:{challenge.mode_code}",
        "preferred_level": "A1",
    }
