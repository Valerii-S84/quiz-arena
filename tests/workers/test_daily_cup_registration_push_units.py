from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_registration_push as push
from tests.game.tournaments_unit_support import NOW_UTC
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_once_claims_and_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _Bot([])
    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        push.AnalyticsRepo,
        "create_daily_cup_push_event_once",
        _async_return(True),
    )

    assert await push._send_daily_cup_registration_push_once(
        bot=bot,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        user_id=11,
        telegram_user_id=101,
        text="text",
        tournament_id_text="tid",
        happened_at=NOW_UTC,
        sent_event_type="sent",
    )
    assert bot.sent == [101]


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_once_skips_unclaimed_or_failed_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        push.AnalyticsRepo,
        "create_daily_cup_push_event_once",
        _async_return(False),
    )
    assert not await push._send_daily_cup_registration_push_once(
        bot=_Bot([]),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        user_id=11,
        telegram_user_id=101,
        text="text",
        tournament_id_text="tid",
        happened_at=NOW_UTC,
        sent_event_type="sent",
    )

    monkeypatch.setattr(
        push.AnalyticsRepo,
        "create_daily_cup_push_event_once",
        _async_return(True),
    )
    assert not await push._send_daily_cup_registration_push_once(
        bot=_Bot([RuntimeError("send failed")]),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        user_id=11,
        telegram_user_id=101,
        text="text",
        tournament_id_text="tid",
        happened_at=NOW_UTC,
        sent_event_type="sent",
    )


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_async_counts_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = SimpleNamespace(
        id=uuid4(),
        status="REGISTRATION",
        registration_deadline=NOW_UTC,
    )
    bot = _Bot([])
    calls = {"targets": 0}

    async def _targets(_session, **_kwargs):
        calls["targets"] += 1
        if calls["targets"] == 1:
            return [(11, 101), (22, 102), (33, 103)]
        return []

    async def _send_once(**kwargs) -> bool:
        return kwargs["user_id"] == 22

    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(push, "ensure_daily_cup_registration_tournament", _async_return(tournament))
    monkeypatch.setattr(push.UsersRepo, "list_daily_cup_push_targets", _targets)
    monkeypatch.setattr(push, "list_already_pushed_user_ids", _async_return({11}))
    monkeypatch.setattr(push, "_send_daily_cup_registration_push_once", _send_once)

    result = await push.send_daily_cup_registration_push_async(
        now_utc_factory=lambda: NOW_UTC,
        bot_factory=lambda: bot,
        text_key="msg.daily_cup.push.registration",
        log_event="event",
        sent_event_type="sent",
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
    )

    assert result == {"processed": 1, "users_scanned_total": 3, "sent_total": 1, "skipped_total": 2}
    assert bot.closed


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_async_returns_zero_when_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        push,
        "ensure_daily_cup_registration_tournament",
        _async_return(SimpleNamespace(status="COMPLETED")),
    )

    result = await push.send_daily_cup_registration_push_async(
        now_utc_factory=lambda: NOW_UTC,
        bot_factory=lambda: _Bot([]),
        text_key="msg.daily_cup.push.registration",
        log_event="event",
        sent_event_type="sent",
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
    )

    assert result == {"processed": 0, "users_scanned_total": 0, "sent_total": 0, "skipped_total": 0}


class _Bot:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self.sent: list[int] = []
        self.closed = False
        self.session = SimpleNamespace(close=self._close)

    async def send_message(self, *, chat_id: int, **_kwargs) -> None:
        outcome = self._outcomes.pop(0) if self._outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        self.sent.append(chat_id)

    async def _close(self) -> None:
        self.closed = True


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
