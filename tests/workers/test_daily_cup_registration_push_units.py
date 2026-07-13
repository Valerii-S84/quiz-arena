from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_registration_push as push
from app.workers.tasks import daily_cup_registration_push_outcome as push_outcome
from tests.game.tournaments_unit_support import NOW_UTC
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_once_claims_and_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _Bot([])
    delivery_calls: list[dict[str, object]] = []
    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(push, "prepare_telegram_delivery", _prepare_delivery(True))
    monkeypatch.setattr(
        push, "record_daily_cup_registration_push_sent", _capture_async(delivery_calls)
    )
    monkeypatch.setattr(push, "mark_telegram_delivery_failed", _capture_async([]))

    assert await push._send_daily_cup_registration_push_once(
        run=_push_run(bot=bot),
        target=_push_target(),
        user_id=11,
    )
    assert bot.sent == [101]
    assert cast(Any, delivery_calls[0]["target"]).idempotency_key.startswith("telegram-delivery:")


@pytest.mark.asyncio
async def test_send_daily_cup_registration_push_once_skips_duplicate_or_failed_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(push, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(push, "prepare_telegram_delivery", _prepare_delivery(False))
    monkeypatch.setattr(
        push,
        "record_daily_cup_registration_push_sent",
        _unexpected_async("analytics must not be written for skipped delivery"),
    )
    assert not await push._send_daily_cup_registration_push_once(
        run=_push_run(bot=_Bot([])),
        target=_push_target(),
        user_id=11,
    )

    failed_calls: list[dict[str, object]] = []
    monkeypatch.setattr(push, "prepare_telegram_delivery", _prepare_delivery(True))
    monkeypatch.setattr(push, "mark_telegram_delivery_failed", _capture_async(failed_calls))
    failed_bot = _Bot([RuntimeError("send failed")])
    assert not await push._send_daily_cup_registration_push_once(
        run=_push_run(bot=failed_bot),
        target=_push_target(),
        user_id=11,
    )
    assert cast(BaseException, failed_calls[0]["exc"]).args == ("send failed",)


@pytest.mark.asyncio
async def test_registration_push_outcome_records_event_before_terminal_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _analytics(*_args, **_kwargs) -> bool:
        calls.append("analytics")
        return True

    async def _sent(*_args, **_kwargs) -> int:
        calls.append("sent")
        return 1

    monkeypatch.setattr(push_outcome.AnalyticsRepo, "create_daily_cup_push_event_once", _analytics)
    monkeypatch.setattr(push_outcome.TelegramDeliveryAttemptsRepo, "mark_sent", _sent)
    await push_outcome.record_daily_cup_registration_push_sent(
        target=cast(Any, SimpleNamespace(idempotency_key="push")),
        user_id=11,
        event_type="sent",
        tournament_id="tid",
        happened_at=NOW_UTC,
        session_local=SessionLocalStub(),
    )

    assert calls == ["analytics", "sent"]


@pytest.mark.asyncio
async def test_registration_push_outcome_does_not_mark_sent_when_event_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_calls: list[object] = []

    async def _analytics(*_args, **_kwargs) -> bool:
        raise RuntimeError("analytics failed")

    async def _sent(*_args, **_kwargs) -> int:
        sent_calls.append(object())
        return 1

    monkeypatch.setattr(push_outcome.AnalyticsRepo, "create_daily_cup_push_event_once", _analytics)
    monkeypatch.setattr(push_outcome.TelegramDeliveryAttemptsRepo, "mark_sent", _sent)
    with pytest.raises(RuntimeError, match="analytics failed"):
        await push_outcome.record_daily_cup_registration_push_sent(
            target=cast(Any, SimpleNamespace(idempotency_key="push")),
            user_id=11,
            event_type="sent",
            tournament_id="tid",
            happened_at=NOW_UTC,
            session_local=SessionLocalStub(),
        )

    assert sent_calls == []


@pytest.mark.asyncio
async def test_registration_push_outcome_fails_when_terminal_cas_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _analytics(*_args, **_kwargs) -> bool:
        return True

    async def _sent(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(push_outcome.AnalyticsRepo, "create_daily_cup_push_event_once", _analytics)
    monkeypatch.setattr(push_outcome.TelegramDeliveryAttemptsRepo, "mark_sent", _sent)
    with pytest.raises(RuntimeError, match="terminal lease was lost"):
        await push_outcome.record_daily_cup_registration_push_sent(
            target=cast(Any, SimpleNamespace(idempotency_key="push")),
            user_id=11,
            event_type="sent",
            tournament_id="tid",
            happened_at=NOW_UTC,
            session_local=SessionLocalStub(),
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
    monkeypatch.setattr(push, "record_telegram_delivery_skipped", _capture_async([]))
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


def _push_run(*, bot: _Bot) -> push.DailyCupRegistrationPushRun:
    return push.DailyCupRegistrationPushRun(
        bot=bot,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        flow="daily_cup_invite_registration_push",
        task_name="daily_cup_invite_registration_push",
        text="text",
        tournament_id_text="tid",
        happened_at=NOW_UTC,
        sent_event_type="sent",
    )


def _push_target():
    return push.daily_cup_delivery_target(
        flow="daily_cup_invite_registration_push",
        task_name="daily_cup_invite_registration_push",
        tournament_id_text="tid",
        user_id=11,
        telegram_user_id=101,
    )


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _prepare_delivery(should_send: bool):
    async def _inner(**kwargs):
        return SimpleNamespace(
            should_send=should_send,
            idempotency_key=kwargs["target"].idempotency_key,
        )

    return _inner


def _capture_async(calls: list[dict[str, object]]):
    async def _inner(**kwargs):
        calls.append(kwargs)

    return _inner


def _unexpected_async(message: str):
    async def _inner(*_args, **_kwargs):
        raise AssertionError(message)

    return _inner
