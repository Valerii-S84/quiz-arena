from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.service.friend_challenges_question_plan import (
    berlin_day_start_utc,
    resolve_tournament_rounds,
    select_duel_question_ids,
)
from app.game.sessions.service.levels import _friend_challenge_level_for_round
from tests.game.friend_challenges_unit_support import Session

UTC = timezone.utc


@pytest.mark.parametrize("rounds", [5, 7, 12])
def test_resolve_tournament_rounds_accepts_supported_formats(rounds: int) -> None:
    assert resolve_tournament_rounds(total_rounds=rounds) == rounds


def test_resolve_tournament_rounds_rejects_invalid_format() -> None:
    with pytest.raises(FriendChallengeAccessError):
        resolve_tournament_rounds(total_rounds=6)


def test_berlin_day_start_utc_tracks_local_midnight() -> None:
    now_utc = datetime(2026, 1, 15, 23, 30, tzinfo=UTC)

    result = berlin_day_start_utc(now_utc=now_utc)

    assert result == datetime(2026, 1, 15, 23, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_select_duel_question_ids_uses_tournament_seed_and_round_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    tournament_id = uuid4()

    async def _fake_select_question(_session, mode_code, **kwargs):
        previous_ids = list(kwargs["previous_round_question_ids"])
        calls.append({"mode_code": mode_code, **kwargs})
        calls[-1]["previous_round_question_ids"] = previous_ids
        return SimpleNamespace(question_id=f"q-{len(calls)}")

    monkeypatch.setattr(
        "app.game.sessions.service.select_friend_challenge_question", _fake_select_question
    )

    selected = await select_duel_question_ids(
        Session(),
        mode_code="QUICK_MIX_A1A2",
        total_rounds=3,
        now_utc=datetime(2026, 5, 7, 10, 0, tzinfo=UTC),
        challenge_seed="ignored",
        tournament_id=tournament_id,
        tournament_round_no=2,
        preferred_levels_by_round=("C1", "B2"),
    )

    assert selected == ["q-1", "q-2", "q-3"]
    assert calls[0]["selection_seed"] == f"tournament:{tournament_id}:2:1"
    assert calls[1]["selection_seed"] == f"tournament:{tournament_id}:2:2"
    assert calls[0]["preferred_level"] == "C1"
    assert calls[1]["preferred_level"] == "B2"
    assert calls[2]["preferred_level"] == _friend_challenge_level_for_round(round_number=3)
    assert calls[2]["previous_round_question_ids"] == ["q-1", "q-2"]


@pytest.mark.asyncio
async def test_select_duel_question_ids_uses_direct_seed_without_tournament(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_select_question(_session, mode_code, **kwargs):
        calls.append({"mode_code": mode_code, **kwargs})
        return SimpleNamespace(question_id="direct-q")

    monkeypatch.setattr(
        "app.game.sessions.service.select_friend_challenge_question", _fake_select_question
    )

    await select_duel_question_ids(
        Session(),
        mode_code="QUICK_MIX_A1A2",
        total_rounds=1,
        now_utc=datetime(2026, 5, 7, 10, 0, tzinfo=UTC),
        challenge_seed="abc",
    )

    assert calls[0]["selection_seed"] == "duel:abc:1"
