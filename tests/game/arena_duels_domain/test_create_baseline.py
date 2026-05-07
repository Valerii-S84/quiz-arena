from typing import cast

import pytest

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.game.arena_duels import service as arena_service
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_SOURCE,
)
from app.game.duels.limits import DUEL_ACCESS_FREE
from app.game.sessions.errors import DuelLimitRequiredError
from tests.type_helpers import AsyncSessionStub

from .support import MODE_CODE, NOW_UTC, question_ids, start_result


@pytest.mark.asyncio
async def test_create_arena_duel_baseline_creates_draft_attempt_and_starts_round_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_select_questions(*_args, **kwargs):
        captured["select_questions"] = kwargs
        return question_ids()

    async def fake_create_duel(*_args, **kwargs):
        captured["duel"] = kwargs["duel"]
        return kwargs["duel"]

    async def fake_create_attempt(*_args, **kwargs):
        captured["attempt"] = kwargs["attempt"]
        return kwargs["attempt"]

    async def fake_start_session(*_args, **kwargs):
        captured["start_session"] = kwargs
        return start_result()

    monkeypatch.setattr(arena_service, "select_duel_question_ids", fake_select_questions)
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_duel", fake_create_duel)
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_attempt", fake_create_attempt)
    monkeypatch.setattr(arena_service, "start_session", fake_start_session)

    result = await arena_service.create_arena_duel_baseline(
        AsyncSessionStub(),
        creator_user_id=11,
        mode_code=MODE_CODE,
        now_utc=NOW_UTC,
        access_type=DUEL_ACCESS_FREE,
    )

    duel = cast(ArenaDuel, captured["duel"])
    attempt = cast(ArenaAttempt, captured["attempt"])
    start_kwargs = cast(dict[str, object], captured["start_session"])
    select_kwargs = cast(dict[str, object], captured["select_questions"])
    assert duel.status == ARENA_DUEL_STATUS_DRAFT
    assert duel.question_ids == question_ids()
    assert duel.access_type == DUEL_ACCESS_FREE
    assert duel.baseline_attempt_id is None
    assert attempt.arena_duel_id == duel.id
    assert attempt.role == ARENA_ATTEMPT_ROLE_CREATOR_BASELINE
    assert attempt.access_type == DUEL_ACCESS_FREE
    assert start_kwargs["source"] == ARENA_SOURCE
    assert start_kwargs["arena_attempt_id"] == attempt.id
    assert start_kwargs["arena_round"] == 1
    assert start_kwargs["duel_limit_checked"] is True
    assert select_kwargs["total_rounds"] == 7
    assert select_kwargs["challenge_seed"] == str(duel.id)
    assert result.baseline_attempt_id == attempt.id
    assert result.duel.status == ARENA_DUEL_STATUS_DRAFT


@pytest.mark.asyncio
async def test_create_arena_duel_baseline_requires_resolved_access_before_creating_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_create(*_args, **_kwargs):
        pytest.fail("Arena rows must not be created before the duel-limit gate")

    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_duel", unexpected_create)
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_attempt", unexpected_create)

    with pytest.raises(DuelLimitRequiredError):
        await arena_service.create_arena_duel_baseline(
            AsyncSessionStub(),
            creator_user_id=11,
            mode_code=MODE_CODE,
            now_utc=NOW_UTC,
            access_type="",
        )
