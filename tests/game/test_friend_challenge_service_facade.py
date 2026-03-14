from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.game.friend_challenges import service_facade
from app.game.sessions.service import GameSessionService

NOW_UTC = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_create_challenge_delegates_to_game_session_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    async def _fake_create_challenge(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(GameSessionService, "create_friend_challenge", _fake_create_challenge)

    result = await service_facade.FriendChallengeServiceFacade.create_challenge(
        object(),
        creator_user_id=10,
        mode_code="CLASSIC",
        now_utc=NOW_UTC,
        total_rounds=3,
    )

    assert result is expected
    assert captured["kwargs"] == {
        "creator_user_id": 10,
        "mode_code": "CLASSIC",
        "now_utc": NOW_UTC,
        "total_rounds": 3,
    }


@pytest.mark.asyncio
async def test_create_rematch_delegates_to_game_session_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    async def _fake_create_rematch(*args, **kwargs):
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(GameSessionService, "create_friend_challenge_rematch", _fake_create_rematch)

    result = await service_facade.FriendChallengeServiceFacade.create_rematch(
        object(),
        initiator_user_id=20,
        challenge_id=CHALLENGE_ID,
        now_utc=NOW_UTC,
    )

    assert result is expected
    assert captured["kwargs"] == {
        "initiator_user_id": 20,
        "challenge_id": CHALLENGE_ID,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_create_best_of_three_delegates_to_game_session_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    async def _fake_create_best_of_three(*args, **kwargs):
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(
        GameSessionService,
        "create_friend_challenge_best_of_three",
        _fake_create_best_of_three,
    )

    result = await service_facade.FriendChallengeServiceFacade.create_best_of_three(
        object(),
        initiator_user_id=30,
        challenge_id=CHALLENGE_ID,
        now_utc=NOW_UTC,
    )

    assert result is expected
    assert captured["kwargs"] == {
        "initiator_user_id": 30,
        "challenge_id": CHALLENGE_ID,
        "now_utc": NOW_UTC,
        "best_of": 3,
    }


@pytest.mark.asyncio
async def test_create_series_next_game_delegates_to_game_session_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    async def _fake_create_series_next_game(*args, **kwargs):
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(
        GameSessionService,
        "create_friend_challenge_series_next_game",
        _fake_create_series_next_game,
    )

    result = await service_facade.FriendChallengeServiceFacade.create_series_next_game(
        object(),
        initiator_user_id=40,
        challenge_id=CHALLENGE_ID,
        now_utc=NOW_UTC,
    )

    assert result is expected
    assert captured["kwargs"] == {
        "initiator_user_id": 40,
        "challenge_id": CHALLENGE_ID,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_start_round_delegates_to_game_session_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    async def _fake_start_round(*args, **kwargs):
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(GameSessionService, "start_friend_challenge_round", _fake_start_round)

    result = await service_facade.FriendChallengeServiceFacade.start_round(
        object(),
        user_id=50,
        challenge_id=CHALLENGE_ID,
        idempotency_key="idem-1",
        now_utc=NOW_UTC,
    )

    assert result is expected
    assert captured["kwargs"] == {
        "user_id": 50,
        "challenge_id": CHALLENGE_ID,
        "idempotency_key": "idem-1",
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_get_snapshot_for_user_delegates_to_game_session_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    async def _fake_get_snapshot(*args, **kwargs):
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(
        GameSessionService, "get_friend_challenge_snapshot_for_user", _fake_get_snapshot
    )

    result = await service_facade.FriendChallengeServiceFacade.get_snapshot_for_user(
        object(),
        user_id=60,
        challenge_id=CHALLENGE_ID,
        now_utc=NOW_UTC,
    )

    assert result is expected
    assert captured["kwargs"] == {
        "user_id": 60,
        "challenge_id": CHALLENGE_ID,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_get_series_score_for_user_delegates_to_game_session_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected = (2, 1, 3, 2)

    async def _fake_get_series_score(*args, **kwargs):
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(
        GameSessionService, "get_friend_series_score_for_user", _fake_get_series_score
    )

    result = await service_facade.FriendChallengeServiceFacade.get_series_score_for_user(
        object(),
        user_id=70,
        challenge_id=CHALLENGE_ID,
        now_utc=NOW_UTC,
    )

    assert result == expected
    assert captured["kwargs"] == {
        "user_id": 70,
        "challenge_id": CHALLENGE_ID,
        "now_utc": NOW_UTC,
    }
