from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers.tasks import daily_cup_async, daily_cup_core
from tests.game.tournaments_unit_support import NOW_UTC, participant_row, tournament_row
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_daily_cup_core_emits_events_and_persists_message_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    updates: list[dict[str, object]] = []

    async def _emit(_session, **kwargs) -> None:
        events.append(kwargs)

    async def _missing(_session, **kwargs) -> None:
        updates.append({"missing": kwargs})

    async def _set(_session, **kwargs) -> None:
        updates.append({"set": kwargs})

    monkeypatch.setattr(daily_cup_core, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(daily_cup_core, "emit_analytics_event", _emit)
    monkeypatch.setattr(
        daily_cup_core.TournamentParticipantsRepo,
        "set_standings_message_id_if_missing",
        _missing,
    )
    monkeypatch.setattr(daily_cup_core.TournamentParticipantsRepo, "set_standings_message_id", _set)

    await daily_cup_core.emit_daily_cup_events(
        now_utc_value=NOW_UTC,
        events=[{"event_type": "daily_cup_started", "payload": "bad"}],
    )
    await daily_cup_core.persist_daily_cup_standings_message_ids(
        tournament_id=tournament_row().id,
        new_message_ids={11: 101},
        replaced_message_ids={22: 202},
    )

    assert events[0]["payload"] == {}
    assert {next(iter(item)) for item in updates} == {"missing", "set"}


@pytest.mark.asyncio
async def test_send_daily_cup_canceled_messages_continues_then_requests_retry() -> None:
    bot = _Bot([RuntimeError("blocked"), None])
    delivery_kwargs: list[dict[str, object]] = []

    async def _deliver_once(_session_local, *, send, **kwargs):
        delivery_kwargs.append(kwargs)
        await send()
        return SimpleNamespace(status="SENT")

    with pytest.raises(daily_cup_core.DailyCupCancelDeliveryRetryNeeded) as exc_info:
        await daily_cup_core.send_daily_cup_canceled_messages(
            telegram_targets=[101, 102],
            tournament_id="tid",
            bot_factory=lambda: bot,
            session_local=SimpleNamespace(),
            deliver_once=_deliver_once,
        )

    assert bot.sent == [102]
    assert bot.closed
    assert exc_info.value.tournament_id == "tid"
    assert exc_info.value.retry_after_seconds == 60
    assert [kwargs["allow_stale_pending_replay_send"] for kwargs in delivery_kwargs] == [True, True]
    assert [kwargs["retry_claim_ttl_seconds"] for kwargs in delivery_kwargs] == [300, 300]
    assert all(
        getattr(kwargs["attempt"], "safe_context") == {"pending_replay_safe": True}
        for kwargs in delivery_kwargs
    )


@pytest.mark.asyncio
async def test_send_daily_cup_canceled_messages_uses_retry_outcome_delay() -> None:
    bot = _Bot([None, None])
    outcomes = iter(
        [
            SimpleNamespace(status="RETRY", retry_after_seconds=47),
            SimpleNamespace(status="SENT", retry_after_seconds=None),
        ]
    )
    delivery_calls = 0

    async def _deliver_once(_session_local, **_kwargs):
        nonlocal delivery_calls
        delivery_calls += 1
        return next(outcomes)

    with pytest.raises(daily_cup_core.DailyCupCancelDeliveryRetryNeeded) as exc_info:
        await daily_cup_core.send_daily_cup_canceled_messages(
            telegram_targets=[101, 102],
            tournament_id="tid",
            bot_factory=lambda: bot,
            session_local=SimpleNamespace(),
            deliver_once=_deliver_once,
        )

    assert delivery_calls == 2
    assert bot.closed
    assert exc_info.value.retry_after_seconds == 47


@pytest.mark.asyncio
async def test_close_daily_cup_registration_cancels_when_too_few_participants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(type="DAILY_ARENA")
    canceled_targets: list[int] = []
    cancel_tournament_ids: list[str] = []
    participants = [participant_row(tournament_id=tournament.id, user_id=11)]

    async def _emit(*, events: list[dict[str, object]], **_kwargs) -> None:
        if events:
            canceled_targets.append(0)

    async def _send(*, telegram_targets: list[int], tournament_id: str, **_kwargs) -> None:
        cancel_tournament_ids.append(tournament_id)
        canceled_targets.extend(telegram_targets)

    monkeypatch.setattr(daily_cup_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: NOW_UTC)
    monkeypatch.setattr(
        daily_cup_async,
        "ensure_daily_cup_registration_tournament",
        _async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_async.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        _async_return(participants),
    )
    monkeypatch.setattr(
        daily_cup_async.UsersRepo,
        "list_by_ids",
        _async_return([SimpleNamespace(telegram_user_id=101)]),
    )
    monkeypatch.setattr(daily_cup_async, "emit_daily_cup_events", _emit)
    monkeypatch.setattr(daily_cup_async, "send_daily_cup_canceled_messages", _send)

    result = await daily_cup_async.close_daily_cup_registration_and_start_async()

    assert result["canceled"] == 1
    assert result["started"] == 0
    assert canceled_targets == [0, 101]
    assert cancel_tournament_ids == [str(tournament.id)]


@pytest.mark.asyncio
async def test_close_daily_cup_registration_retries_committed_cancel_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(type="DAILY_ARENA", status="CANCELED")
    participants = [participant_row(tournament_id=tournament.id, user_id=11)]
    emitted_events: list[dict[str, object]] = []
    canceled_targets: list[int] = []
    cancel_tournament_ids: list[str] = []

    async def _emit(*, events: list[dict[str, object]], **_kwargs) -> None:
        emitted_events.extend(events)

    async def _send(*, telegram_targets: list[int], tournament_id: str, **_kwargs) -> None:
        canceled_targets.extend(telegram_targets)
        cancel_tournament_ids.append(tournament_id)

    monkeypatch.setattr(daily_cup_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: NOW_UTC)
    monkeypatch.setattr(
        daily_cup_async,
        "ensure_daily_cup_registration_tournament",
        _async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_async.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        _async_return(participants),
    )
    monkeypatch.setattr(
        daily_cup_async.UsersRepo,
        "list_by_ids",
        _async_return([SimpleNamespace(telegram_user_id=101)]),
    )
    monkeypatch.setattr(daily_cup_async, "emit_daily_cup_events", _emit)
    monkeypatch.setattr(daily_cup_async, "send_daily_cup_canceled_messages", _send)

    result = await daily_cup_async.close_daily_cup_registration_and_start_async()

    assert result == {
        "processed": 1,
        "canceled": 1,
        "started": 0,
        "participants_total": 1,
    }
    assert canceled_targets == [101]
    assert cancel_tournament_ids == [str(tournament.id)]
    assert emitted_events == []


@pytest.mark.asyncio
async def test_close_daily_cup_registration_retry_loads_exact_canceled_tournament(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(type="DAILY_ARENA", status="CANCELED")
    participants = [participant_row(tournament_id=tournament.id, user_id=11)]
    loaded_tournament_ids: list[object] = []
    cancel_tournament_ids: list[str] = []

    async def _load(_session, tournament_id):
        loaded_tournament_ids.append(tournament_id)
        return tournament

    async def _send(*, tournament_id: str, **_kwargs) -> None:
        cancel_tournament_ids.append(tournament_id)

    async def _unexpected_current_tournament(**_kwargs):
        raise AssertionError("retry must not select the current Daily Cup window")

    monkeypatch.setattr(daily_cup_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: NOW_UTC)
    monkeypatch.setattr(
        daily_cup_async,
        "ensure_daily_cup_registration_tournament",
        _unexpected_current_tournament,
    )
    monkeypatch.setattr(daily_cup_async.TournamentsRepo, "get_by_id_for_update", _load)
    monkeypatch.setattr(
        daily_cup_async.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        _async_return(participants),
    )
    monkeypatch.setattr(
        daily_cup_async.UsersRepo,
        "list_by_ids",
        _async_return([SimpleNamespace(telegram_user_id=101)]),
    )
    monkeypatch.setattr(daily_cup_async, "emit_daily_cup_events", _async_return(None))
    monkeypatch.setattr(daily_cup_async, "send_daily_cup_canceled_messages", _send)

    result = await daily_cup_async.close_daily_cup_registration_and_start_async(
        tournament_id=str(tournament.id),
    )

    assert result["canceled"] == 1
    assert loaded_tournament_ids == [tournament.id]
    assert cancel_tournament_ids == [str(tournament.id)]


@pytest.mark.asyncio
async def test_publish_daily_cup_final_results_processes_completed_tournament(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(type="DAILY_ARENA", status="COMPLETED")
    monkeypatch.setattr(daily_cup_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: NOW_UTC)
    monkeypatch.setattr(
        daily_cup_async.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        _async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_async,
        "run_daily_cup_round_messaging_async_with_followups",
        _async_return({"processed": 1}),
    )

    result = await daily_cup_async.publish_daily_cup_final_results_async()

    assert result == {"processed": 1, "published": 1}


class _Bot:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self.sent: list[int] = []
        self.closed = False
        self.session = SimpleNamespace(close=self._close)

    async def send_message(self, *, chat_id: int, **_kwargs) -> None:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        self.sent.append(chat_id)

    async def _close(self) -> None:
        self.closed = True


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
