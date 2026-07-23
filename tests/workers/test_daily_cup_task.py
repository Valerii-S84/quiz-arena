from typing import Any

import pytest

from app.workers.tasks import daily_cup


@pytest.mark.parametrize(
    ("wrapper_name", "async_name", "task_name", "schedule_key"),
    (
        (
            "send_invite",
            "send_daily_cup_invite_async",
            "app.workers.tasks.daily_cup.send_invite",
            "daily-cup-send-invite-on-demand",
        ),
        (
            "send_invite_registration",
            "send_daily_cup_invite_registration_async",
            "app.workers.tasks.daily_cup.send_invite_registration",
            "daily-cup-send-invite-registration",
        ),
        (
            "open_registration",
            "open_daily_cup_registration_async",
            "app.workers.tasks.daily_cup.open_registration",
            "daily-cup-open-registration",
        ),
        (
            "send_last_call_reminder",
            "send_daily_cup_last_call_reminder_async",
            "app.workers.tasks.daily_cup.send_last_call_reminder",
            "daily-cup-last-call-reminder",
        ),
        (
            "send_prestart_reminder",
            "send_daily_cup_prestart_reminder_async",
            "app.workers.tasks.daily_cup.send_prestart_reminder",
            "daily-cup-prestart-reminder",
        ),
        (
            "publish_final_results",
            "publish_daily_cup_final_results_async",
            "app.workers.tasks.daily_cup.publish_final_results",
            "daily-cup-publish-final-results",
        ),
        (
            "send_turn_reminders",
            "run_daily_cup_turn_reminders_async",
            "app.workers.tasks.daily_cup.send_turn_reminders",
            "daily-cup-turn-reminders",
        ),
        (
            "close_registration_and_start",
            "close_daily_cup_registration_and_start_async",
            "app.workers.tasks.daily_cup.close_registration_and_start",
            "daily-cup-close-registration",
        ),
        (
            "advance_rounds",
            "advance_daily_cup_rounds_async",
            "app.workers.tasks.daily_cup.advance_rounds",
            "daily-cup-round-advance",
        ),
    ),
)
def test_daily_cup_task_wrappers_record_heartbeats(
    monkeypatch: pytest.MonkeyPatch,
    wrapper_name: str,
    async_name: str,
    task_name: str,
    schedule_key: str,
) -> None:
    expected_result = {"processed": 1}
    tracked: dict[str, object] = {}

    async def _fake_async() -> dict[str, int]:
        return expected_result

    def _run_tracked_async_job(
        *,
        task_name: str,
        schedule_key: str,
        awaitable: Any,
    ) -> dict[str, int]:
        tracked.update(task_name=task_name, schedule_key=schedule_key)
        awaitable.close()
        return expected_result

    monkeypatch.setattr(daily_cup, async_name, _fake_async)
    monkeypatch.setattr(daily_cup, "run_tracked_async_job", _run_tracked_async_job)

    result = getattr(daily_cup, wrapper_name)()

    assert result == expected_result
    assert tracked == {"task_name": task_name, "schedule_key": schedule_key}
