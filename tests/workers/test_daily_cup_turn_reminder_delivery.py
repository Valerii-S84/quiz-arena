from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.workers.tasks import daily_cup_turn_reminder_delivery as reminder_delivery
from tests.workers.daily_cup_turn_reminder_test_support import RecordingBot


@pytest.mark.asyncio
async def test_turn_reminder_idempotency_is_versioned_per_reminder_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_keys: set[str] = set()
    prepared_target_ids: list[str] = []
    bot = RecordingBot()

    async def _prepare(**kwargs):
        target = kwargs["target"]
        prepared_target_ids.append(target.target_id)
        return SimpleNamespace(
            should_send=target.idempotency_key not in sent_keys,
            idempotency_key=target.idempotency_key,
        )

    async def _sent(**kwargs):
        sent_keys.add(str(kwargs["idempotency_key"]))

    monkeypatch.setattr(reminder_delivery, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(reminder_delivery, "mark_telegram_delivery_sent", _sent)

    first = await _deliver(bot, [_reminder(target_user_id=10, chat_id=10010, window_key="initial")])
    second_window = "2026-07-12T12:00:00+00:00"
    second = await _deliver(
        bot,
        [
            _reminder(target_user_id=10, chat_id=10010, window_key=second_window),
            _reminder(target_user_id=10, chat_id=10010, window_key=second_window),
            _reminder(target_user_id=20, chat_id=10020, window_key=second_window),
        ],
    )

    assert first.sent_total == 1
    assert second.sent_total == 2
    assert second.skipped_total == 1
    assert [int(message["chat_id"]) for message in bot.messages] == [10010, 10010, 10020]
    assert prepared_target_ids == [
        "11111111-1111-1111-1111-111111111111:10:initial",
        f"11111111-1111-1111-1111-111111111111:10:{second_window}",
        f"11111111-1111-1111-1111-111111111111:10:{second_window}",
        f"11111111-1111-1111-1111-111111111111:20:{second_window}",
    ]


async def _deliver(
    bot: RecordingBot,
    reminders: list[reminder_delivery.ReminderItem],
) -> reminder_delivery.ReminderDeliveryResult:
    return await reminder_delivery.deliver_reminders(
        reminders=reminders,
        build_bot_fn=lambda: bot,
        build_keyboard=lambda **kwargs: {"challenge_id": kwargs["play_challenge_id"]},
        build_text=lambda **kwargs: f"{kwargs['opponent_label']} {kwargs['deadline_text']}",
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )


def _reminder(
    *,
    target_user_id: int,
    chat_id: int,
    window_key: str,
) -> reminder_delivery.ReminderItem:
    return reminder_delivery.ReminderItem(
        tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        challenge_id="11111111-1111-1111-1111-111111111111",
        target_user_id=target_user_id,
        target_chat_id=chat_id,
        window_key=window_key,
        opponent_label="Spieler",
        deadline_text="12:30",
    )
