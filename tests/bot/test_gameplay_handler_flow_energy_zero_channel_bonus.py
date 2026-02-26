from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.bot.handlers.gameplay_flows import energy_zero_flow
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback


class _FakeOfferService:
    def __init__(self, result=None) -> None:
        self._result = result
        self.calls = 0

    async def evaluate_and_log_offer(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        return self._result


class _ChannelBonusEnabled:
    @staticmethod
    async def can_show_prompt(session, *, user_id: int) -> bool:
        del session, user_id
        return True

    @staticmethod
    def resolve_channel_url() -> str:
        return "https://t.me/quiz_arena_test"


class _ChannelBonusClaimed:
    @staticmethod
    async def can_show_prompt(session, *, user_id: int) -> bool:
        del session, user_id
        return False

    @staticmethod
    def resolve_channel_url() -> str:
        return "https://t.me/quiz_arena_test"


@pytest.mark.asyncio
async def test_energy_zero_shows_channel_bonus_when_not_claimed(monkeypatch) -> None:
    emitted_events: list[str] = []

    async def _fake_emit(*args, **kwargs):
        del args
        emitted_events.append(str(kwargs["event_type"]))

    monkeypatch.setattr(energy_zero_flow, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(data="x", from_user=SimpleNamespace(id=1))
    offer_service = _FakeOfferService()

    await energy_zero_flow.handle_energy_insufficient(
        callback,
        session=SimpleNamespace(),
        user_id=11,
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
        offer_service=offer_service,
        offer_logging_error=RuntimeError,
        offer_idempotency_key="offer:energy:test",
        channel_bonus_service=_ChannelBonusEnabled,
    )

    assert offer_service.calls == 0
    assert callback.message.answers[0].text is not None
    assert "Lerne täglich kostenlos Deutsch" in callback.message.answers[0].text
    assert "channel_bonus_shown" in emitted_events


@pytest.mark.asyncio
async def test_energy_zero_does_not_show_channel_bonus_when_already_claimed() -> None:
    callback = DummyCallback(data="x", from_user=SimpleNamespace(id=1))
    offer_service = _FakeOfferService(result=None)

    await energy_zero_flow.handle_energy_insufficient(
        callback,
        session=SimpleNamespace(),
        user_id=22,
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
        offer_service=offer_service,
        offer_logging_error=RuntimeError,
        offer_idempotency_key="offer:energy:test",
        channel_bonus_service=_ChannelBonusClaimed,
    )

    assert offer_service.calls == 1
    assert callback.message.answers[0].text == TEXTS_DE["msg.energy.empty.body"]
