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


@pytest.mark.asyncio
async def test_energy_zero_uses_offer_flow() -> None:
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
    )

    assert offer_service.calls == 1
    assert callback.message.answers[0].text == TEXTS_DE["msg.energy.empty.body"]


@pytest.mark.asyncio
async def test_energy_zero_uses_empty_energy_message_without_offer() -> None:
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
    )

    assert offer_service.calls == 1
    assert callback.message.answers[0].text == TEXTS_DE["msg.energy.empty.body"]
