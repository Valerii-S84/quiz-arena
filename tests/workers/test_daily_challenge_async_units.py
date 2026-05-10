from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers.tasks import daily_challenge_async
from app.workers.tasks.daily_challenge_config import DAILY_PUSH_KIND_EVENING_REMINDER
from tests.workers.payments_reliability_async_support import SessionLocalStub


def test_daily_push_kind_and_text_helpers() -> None:
    assert daily_challenge_async._resolve_push_kind(" morning ") == "MORNING"
    assert "1" in daily_challenge_async._build_push_text(push_kind="MORNING", current_streak=0)
    evening_text = daily_challenge_async._build_push_text(
        push_kind=DAILY_PUSH_KIND_EVENING_REMINDER,
        current_streak=3,
    )
    assert "3" in evening_text

    with pytest.raises(ValueError):
        daily_challenge_async._resolve_push_kind("bad-kind")


@pytest.mark.asyncio
async def test_run_daily_question_set_precompute_async(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(daily_challenge_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        daily_challenge_async,
        "ensure_daily_question_set",
        _async_return([1, 2, 3]),
    )

    result = await daily_challenge_async.run_daily_question_set_precompute_async()

    assert result["questions_total"] == 3
    assert "berlin_date" in result


@pytest.mark.asyncio
async def test_run_daily_push_notifications_counts_sent_and_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _Bot(send_outcomes=[None, RuntimeError("send failed")])
    calls = {"targets": 0, "created": 0}

    async def _targets(_session, **_kwargs):
        calls["targets"] += 1
        if calls["targets"] == 1:
            return [(1, 101, 0), (2, 102, 2), (3, 103, 1)]
        return []

    async def _create_once(_session, **_kwargs):
        calls["created"] += 1
        return calls["created"] != 2

    monkeypatch.setattr(daily_challenge_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(daily_challenge_async, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_challenge_async.UsersRepo, "list_daily_push_targets", _targets)
    monkeypatch.setattr(daily_challenge_async.DailyPushLogsRepo, "create_once", _create_once)
    monkeypatch.setattr(daily_challenge_async, "build_daily_push_keyboard", lambda: None)

    result = await daily_challenge_async.run_daily_push_notifications_async(
        batch_size=0,
        push_kind="MORNING",
    )

    assert result["batch_size"] == 1
    assert result["users_scanned_total"] == 3
    assert result["sent_total"] == 1
    assert result["skipped_total"] == 2
    assert bot.closed


class _Bot:
    def __init__(self, *, send_outcomes: list[object]) -> None:
        self._send_outcomes = send_outcomes
        self.closed = False
        self.session = SimpleNamespace(close=self._close)

    async def send_message(self, **_kwargs) -> None:
        outcome = self._send_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

    async def _close(self) -> None:
        self.closed = True


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
