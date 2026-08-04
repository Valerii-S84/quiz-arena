from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from app.workers.tasks import (
    daily_cup,
    daily_cup_config,
    daily_cup_messaging,
    daily_cup_nonfinishers_summary,
    daily_cup_proof_cards,
)

DISABLED_RESULT = {"processed": 0, "disabled": 1}


def _unexpected_call(*_args: object, **_kwargs: object) -> None:
    pytest.fail("disabled Daily Cup task attempted to execute or enqueue work")


@pytest.mark.parametrize(
    ("task", "async_name"),
    [
        (daily_cup.send_invite, "send_daily_cup_invite_async"),
        (daily_cup.send_invite_registration, "send_daily_cup_invite_registration_async"),
        (daily_cup.open_registration, "open_daily_cup_registration_async"),
        (daily_cup.send_last_call_reminder, "send_daily_cup_last_call_reminder_async"),
        (daily_cup.send_prestart_reminder, "send_daily_cup_prestart_reminder_async"),
        (daily_cup.publish_final_results, "publish_daily_cup_final_results_async"),
        (daily_cup.send_turn_reminders, "run_daily_cup_turn_reminders_async"),
        (
            daily_cup.close_registration_and_start,
            "close_daily_cup_registration_and_start_async",
        ),
        (daily_cup.advance_rounds, "advance_daily_cup_rounds_async"),
    ],
)
def test_disabled_primary_task_does_not_execute(
    monkeypatch: pytest.MonkeyPatch,
    task: Callable[[], dict[str, int]],
    async_name: str,
) -> None:
    monkeypatch.setattr(daily_cup_config, "DAILY_CUP_ENABLED", False)
    monkeypatch.setattr(daily_cup, async_name, _unexpected_call)
    monkeypatch.setattr(daily_cup, "run_async_job", _unexpected_call)

    assert task() == DISABLED_RESULT


@pytest.mark.parametrize(
    ("module", "task", "async_name", "kwargs"),
    [
        (
            daily_cup_messaging,
            daily_cup_messaging.run_daily_cup_round_messaging,
            "run_daily_cup_round_messaging_async_with_followups",
            {"tournament_id": "daily-cup-disabled"},
        ),
        (
            daily_cup_proof_cards,
            daily_cup_proof_cards.run_daily_cup_proof_cards,
            "run_daily_cup_proof_cards_async",
            {"tournament_id": "daily-cup-disabled"},
        ),
        (
            daily_cup_nonfinishers_summary,
            daily_cup_nonfinishers_summary.run_daily_cup_nonfinishers_summary,
            "run_daily_cup_nonfinishers_summary_async",
            {"tournament_id": "daily-cup-disabled"},
        ),
    ],
)
def test_disabled_queued_followup_task_does_not_execute(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    task: Callable[..., dict[str, int]],
    async_name: str,
    kwargs: dict[str, str],
) -> None:
    monkeypatch.setattr(daily_cup_config, "DAILY_CUP_ENABLED", False)
    monkeypatch.setattr(module, async_name, _unexpected_call)
    monkeypatch.setattr(module, "run_async_job", _unexpected_call)

    assert task(**kwargs) == DISABLED_RESULT


def test_disabled_followup_enqueuers_do_not_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(daily_cup_config, "DAILY_CUP_ENABLED", False)
    monkeypatch.setattr(daily_cup_messaging, "is_celery_task", _unexpected_call)
    monkeypatch.setattr(
        daily_cup_proof_cards, "enqueue_daily_cup_proof_cards_job", _unexpected_call
    )
    monkeypatch.setattr(daily_cup_nonfinishers_summary, "_is_celery_task", _unexpected_call)

    daily_cup_messaging.enqueue_daily_cup_round_messaging(tournament_id="daily-cup-disabled")
    assert (
        daily_cup_proof_cards.enqueue_daily_cup_proof_cards(tournament_id="daily-cup-disabled")
        is False
    )
    daily_cup_nonfinishers_summary.enqueue_daily_cup_nonfinishers_summary(
        tournament_id="daily-cup-disabled"
    )


def test_disabled_user_requested_proof_card_still_enqueues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _record_enqueue(**kwargs: object) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(daily_cup_config, "DAILY_CUP_ENABLED", False)
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards_job",
        _record_enqueue,
    )

    assert daily_cup_proof_cards.enqueue_daily_cup_proof_cards(
        tournament_id="daily-cup-disabled",
        user_id=42,
        delay_seconds=0,
    )
    assert len(calls) == 1
    assert calls[0]["tournament_id"] == "daily-cup-disabled"
    assert calls[0]["user_id"] == 42


def test_disabled_queued_user_requested_proof_card_still_executes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_async(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {"processed": 1, "sent": 1}

    monkeypatch.setattr(daily_cup_config, "DAILY_CUP_ENABLED", False)
    monkeypatch.setattr(daily_cup_proof_cards, "run_daily_cup_proof_cards_async", _fake_async)
    monkeypatch.setattr(daily_cup_proof_cards, "run_async_job", asyncio.run)

    assert daily_cup_proof_cards.run_daily_cup_proof_cards(
        tournament_id="daily-cup-disabled",
        user_id=42,
        initial_delay_seconds=0,
    ) == {"processed": 1, "sent": 1}
    assert len(calls) == 1
    assert calls[0]["tournament_id"] == "daily-cup-disabled"
    assert calls[0]["user_id"] == 42
