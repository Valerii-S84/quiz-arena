from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.workers.tasks import daily_cup_turn_reminder_delivery as reminder_delivery
from app.workers.tasks import daily_cup_turn_reminder_delivery_runtime as reminder_runtime
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
        should_send = target.idempotency_key not in sent_keys
        return SimpleNamespace(
            should_send=should_send,
            idempotency_key=target.idempotency_key,
            status="PENDING" if should_send else "SENT",
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


@pytest.mark.asyncio
async def test_turn_reminder_payload_failure_happens_before_pending_claim() -> None:
    call_order: list[str] = []

    def _keyboard(**_kwargs: Any) -> object:
        call_order.append("payload")
        raise RuntimeError("payload failed")

    async def _prepare(**_kwargs: Any) -> object:
        call_order.append("prepare")
        return SimpleNamespace(should_send=False)

    dependencies = cast(
        Any,
        SimpleNamespace(
            build_delivery_idempotency_key=lambda **_kwargs: "delivery",
            prepare_telegram_delivery=_prepare,
        ),
    )
    context = cast(
        Any,
        SimpleNamespace(
            dependencies=dependencies,
            build_keyboard=_keyboard,
            build_text=lambda **_kwargs: "text",
            happened_at=object(),
        ),
    )

    with pytest.raises(RuntimeError, match="payload failed"):
        await reminder_runtime._deliver_one_reminder(
            context=context,
            state=reminder_runtime.ReminderDeliveryState(),
            reminder=_reminder(target_user_id=10, chat_id=10010, window_key="initial"),
        )

    assert call_order == ["payload"]


@pytest.mark.asyncio
async def test_turn_reminder_blocked_skip_remains_unnotified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _prepare(**_kwargs: Any) -> object:
        return SimpleNamespace(should_send=False, status="SKIPPED")

    monkeypatch.setattr(reminder_delivery, "prepare_telegram_delivery", _prepare)
    reminder = _reminder(target_user_id=10, chat_id=10010, window_key="initial")

    result = await _deliver(RecordingBot(), [reminder])

    assert result.sent_total == 0
    assert result.skipped_total == 1
    assert result.failed_challenge_ids == {reminder.challenge_id}


@pytest.mark.asyncio
async def test_turn_reminders_continue_after_recipient_system_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processed_user_ids: list[int] = []
    bot = RecordingBot()
    reminders = [
        _reminder(target_user_id=10, chat_id=10010, window_key="initial"),
        _reminder(target_user_id=20, chat_id=10020, window_key="initial"),
        _reminder(target_user_id=30, chat_id=10030, window_key="initial"),
    ]

    async def _deliver(*, reminder, **_kwargs):
        processed_user_ids.append(reminder.target_user_id)
        if reminder.target_user_id == 20:
            raise RuntimeError("mark sent failed")

    monkeypatch.setattr(reminder_runtime, "_deliver_one_reminder", _deliver)
    result = await reminder_runtime.deliver_reminders_with_dependencies(
        reminders=reminders,
        build_bot_fn=lambda: bot,
        build_keyboard=lambda **_kwargs: None,
        build_text=lambda **_kwargs: "text",
        logger=SimpleNamespace(),
        dependencies=cast(Any, SimpleNamespace(happened_at=lambda: object())),
    )

    assert processed_user_ids == [10, 20, 30]
    assert result.failed_challenge_ids == {reminders[1].challenge_id}
    assert len(result.system_errors) == 1
    assert str(result.system_errors[0]) == "mark sent failed"
    assert bot.session.closed is True


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
