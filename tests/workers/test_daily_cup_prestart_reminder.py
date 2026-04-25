from __future__ import annotations

import pytest

from app.workers.tasks import daily_cup_prestart_reminder


@pytest.mark.asyncio
async def test_prestart_reminder_delegates_to_registration_push_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_send_daily_cup_registration_push_async(**kwargs):
        captured.update(kwargs)
        return {"processed": 1, "sent_total": 3}

    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "send_daily_cup_registration_push_async",
        _fake_send_daily_cup_registration_push_async,
    )

    result = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()

    assert result == {"processed": 1, "sent_total": 3}
    assert captured["now_utc_factory"] is daily_cup_prestart_reminder.now_utc
    assert captured["bot_factory"] is daily_cup_prestart_reminder.build_bot
    assert captured["text_key"] == "msg.daily_cup.prestart_reminder"
    assert captured["log_event"] == "daily_cup_prestart_reminder_processed"
    assert captured["sent_event_type"] == "daily_cup_prestart_reminder_sent"
    assert captured["logger"] is daily_cup_prestart_reminder.logger
