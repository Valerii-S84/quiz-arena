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
async def test_send_daily_cup_canceled_messages_ignores_send_errors() -> None:
    bot = _Bot([RuntimeError("blocked"), None])

    await daily_cup_core.send_daily_cup_canceled_messages(
        telegram_targets=[101, 102],
        bot_factory=lambda: bot,
    )

    assert bot.sent == [102]
    assert bot.closed


@pytest.mark.asyncio
async def test_close_daily_cup_registration_cancels_when_too_few_participants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(type="DAILY_ARENA")
    canceled_targets: list[int] = []
    participants = [participant_row(tournament_id=tournament.id, user_id=11)]

    async def _emit(*, events: list[dict[str, object]], **_kwargs) -> None:
        if events:
            canceled_targets.append(0)

    async def _send(*, telegram_targets: list[int], **_kwargs) -> None:
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
