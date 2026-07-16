from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.workers.tasks import daily_cup_registration_push as push
from tests.game.tournaments_unit_support import NOW_UTC
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_once_claims_and_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _Bot([])
    attempts: list[TelegramDeliveryAttemptCreate] = []

    async def _deliver_once(
        _session_local, *, attempt: TelegramDeliveryAttemptCreate, send, **_kwargs
    ):
        attempts.append(attempt)
        await send()
        return SimpleNamespace(status="SENT")

    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(push, "deliver_telegram_once", _deliver_once)
    monkeypatch.setattr(
        push.AnalyticsRepo,
        "create_daily_cup_push_event_once",
        _async_return(True),
    )

    assert await push._send_daily_cup_registration_push_once(
        bot=bot,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        item=_push_item(),
    )
    assert bot.sent == [101]
    assert attempts[0].idempotency_key == "daily_cup:sent:tid:11"


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_once_skips_failed_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _failed_delivery(*_args, **_kwargs):
        return SimpleNamespace(status="FAILED")

    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(push, "deliver_telegram_once", _failed_delivery)
    assert not await push._send_daily_cup_registration_push_once(
        bot=_Bot([]),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        item=_push_item(),
    )


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_once_handles_unclassified_send_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _deliver_once(_session_local, *, send, **_kwargs):
        await send()
        return SimpleNamespace(status="SENT")

    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(push, "deliver_telegram_once", _deliver_once)
    assert not await push._send_daily_cup_registration_push_once(
        bot=_Bot([RuntimeError("send failed")]),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        item=_push_item(),
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
        return kwargs["item"].user_id == 22

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


def _push_item() -> push._RegistrationPushItem:
    return push._RegistrationPushItem(
        user_id=11,
        telegram_user_id=101,
        text="text",
        tournament_id_text="tid",
        happened_at=NOW_UTC,
        sent_event_type="sent",
    )
