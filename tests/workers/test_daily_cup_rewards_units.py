from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_winner_reward_grants as grants
from app.workers.tasks import daily_cup_winner_rewards as rewards
from tests.game.tournaments_unit_support import NOW_UTC


@pytest.mark.asyncio
async def test_grant_daily_cup_winner_rewards_filters_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = uuid4()
    context = SimpleNamespace(
        participants_total=13,
        parsed_tournament_id=tournament_id,
        participants=[SimpleNamespace(user_id=11), SimpleNamespace(user_id=22)],
        standings_user_ids=[11, 22, 33],
    )
    monkeypatch.setattr(
        rewards.AnalyticsRepo,
        "list_user_ids_by_event_type_and_tournament",
        _async_return([22]),
    )
    monkeypatch.setattr(rewards, "grant_daily_cup_rank_reward", _async_return(True))

    notifications = await rewards.grant_daily_cup_winner_rewards(
        session=object(),
        context=context,
        now_utc=NOW_UTC,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    assert [notification.user_id for notification in notifications] == [11]


@pytest.mark.asyncio
async def test_grant_daily_cup_winner_rewards_skips_small_tournaments() -> None:
    notifications = await rewards.grant_daily_cup_winner_rewards(
        session=object(),
        context=SimpleNamespace(participants_total=12),
        now_utc=NOW_UTC,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    assert notifications == []


@pytest.mark.asyncio
async def test_send_daily_cup_winner_reward_messages_emits_sent_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    bot = SimpleNamespace(send_message=_async_return(None))
    context = SimpleNamespace(parsed_tournament_id=uuid4(), telegram_targets={11: 101})

    async def _emit(_session, **kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(rewards, "emit_analytics_event", _emit)

    await rewards.send_daily_cup_winner_reward_messages(
        session=object(),
        bot=bot,
        context=context,
        notifications=[rewards.DailyCupWinnerRewardNotification(user_id=11, text="reward")],
        now_utc=NOW_UTC,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    assert events[0]["user_id"] == 11


@pytest.mark.asyncio
async def test_rank_reward_rank_one_existing_ledger_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _NestedSession()
    monkeypatch.setattr(grants.LedgerRepo, "get_by_idempotency_key", _async_return(object()))

    assert await grants.grant_daily_cup_rank_reward(
        session=session,
        tournament_id=uuid4(),
        user_id=11,
        rank=1,
        now_utc=NOW_UTC,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )


@pytest.mark.asyncio
async def test_rank_reward_rank_three_returns_energy_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grants.EnergyService,
        "credit_paid_energy",
        _async_return(SimpleNamespace(amount=5)),
    )

    assert await grants.grant_daily_cup_rank_reward(
        session=_NestedSession(),
        tournament_id=uuid4(),
        user_id=11,
        rank=3,
        now_utc=NOW_UTC,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )


@pytest.mark.asyncio
async def test_rank_reward_logs_and_returns_false_on_error() -> None:
    warnings: list[dict[str, object]] = []

    assert not await grants.grant_daily_cup_rank_reward(
        session=_FailingNestedSession(),
        tournament_id=uuid4(),
        user_id=11,
        rank=2,
        now_utc=NOW_UTC,
        logger=SimpleNamespace(warning=lambda _event, **kwargs: warnings.append(kwargs)),
    )
    assert warnings[0]["rank"] == 2


class _NestedSession:
    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FailingNestedSession(_NestedSession):
    async def __aenter__(self):
        raise RuntimeError("nested failed")


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
