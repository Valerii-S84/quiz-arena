from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.task_heartbeat import run_tracked_async_job
from app.workers.tasks.daily_cup_async import (
    close_daily_cup_registration_and_start_async as _close_daily_cup_registration_and_start_async,
)
from app.workers.tasks.daily_cup_async import (
    open_daily_cup_registration_async as _open_daily_cup_registration_async,
)
from app.workers.tasks.daily_cup_async import (
    publish_daily_cup_final_results_async as _publish_daily_cup_final_results_async,
)
from app.workers.tasks.daily_cup_async import (
    send_daily_cup_invite_async as _send_daily_cup_invite_async,
)
from app.workers.tasks.daily_cup_async import (
    send_daily_cup_invite_registration_async as _send_daily_cup_invite_registration_async,
)
from app.workers.tasks.daily_cup_async import (
    send_daily_cup_last_call_reminder_async as _send_daily_cup_last_call_reminder_async,
)
from app.workers.tasks.daily_cup_messaging import run_daily_cup_round_messaging
from app.workers.tasks.daily_cup_nonfinishers_summary import run_daily_cup_nonfinishers_summary
from app.workers.tasks.daily_cup_prestart_reminder import (
    send_daily_cup_prestart_reminder_async as _send_daily_cup_prestart_reminder_async,
)
from app.workers.tasks.daily_cup_proof_cards import run_daily_cup_proof_cards
from app.workers.tasks.daily_cup_rounds import (
    advance_daily_cup_rounds_async as _advance_daily_cup_rounds_async,
)
from app.workers.tasks.daily_cup_schedule import configure_daily_cup_schedule
from app.workers.tasks.daily_cup_turn_reminder import (
    run_daily_cup_turn_reminders_async as _run_daily_cup_turn_reminders_async,
)

open_daily_cup_registration_async = _open_daily_cup_registration_async
close_daily_cup_registration_and_start_async = _close_daily_cup_registration_and_start_async
advance_daily_cup_rounds_async = _advance_daily_cup_rounds_async
send_daily_cup_invite_registration_async = _send_daily_cup_invite_registration_async
send_daily_cup_invite_async = _send_daily_cup_invite_async
send_daily_cup_last_call_reminder_async = _send_daily_cup_last_call_reminder_async
publish_daily_cup_final_results_async = _publish_daily_cup_final_results_async
send_daily_cup_prestart_reminder_async = _send_daily_cup_prestart_reminder_async
run_daily_cup_turn_reminders_async = _run_daily_cup_turn_reminders_async

__all__ = [
    "advance_rounds",
    "advance_daily_cup_rounds_async",
    "close_daily_cup_registration_and_start_async",
    "close_registration_and_start",
    "open_daily_cup_registration_async",
    "open_registration",
    "publish_daily_cup_final_results_async",
    "publish_final_results",
    "run_daily_cup_proof_cards",
    "run_daily_cup_round_messaging",
    "run_daily_cup_nonfinishers_summary",
    "run_daily_cup_turn_reminders_async",
    "send_invite_registration",
    "send_daily_cup_invite_registration_async",
    "send_daily_cup_invite_async",
    "send_daily_cup_last_call_reminder_async",
    "send_daily_cup_prestart_reminder_async",
    "send_last_call_reminder",
    "send_prestart_reminder",
    "send_turn_reminders",
    "send_invite",
]


@celery_app.task(
    name="app.workers.tasks.daily_cup.send_invite",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def send_invite() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.send_invite"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-send-invite-on-demand",
        awaitable=send_daily_cup_invite_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.send_invite_registration")
def send_invite_registration() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.send_invite_registration"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-send-invite-registration",
        awaitable=send_daily_cup_invite_registration_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.open_registration")
def open_registration() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.open_registration"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-open-registration",
        awaitable=open_daily_cup_registration_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.send_last_call_reminder")
def send_last_call_reminder() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.send_last_call_reminder"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-last-call-reminder",
        awaitable=send_daily_cup_last_call_reminder_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.send_prestart_reminder")
def send_prestart_reminder() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.send_prestart_reminder"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-prestart-reminder",
        awaitable=send_daily_cup_prestart_reminder_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.publish_final_results")
def publish_final_results() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.publish_final_results"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-publish-final-results",
        awaitable=publish_daily_cup_final_results_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.send_turn_reminders")
def send_turn_reminders() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.send_turn_reminders"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-turn-reminders",
        awaitable=run_daily_cup_turn_reminders_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.close_registration_and_start")
def close_registration_and_start() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.close_registration_and_start"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-close-registration",
        awaitable=close_daily_cup_registration_and_start_async(),
    )


@celery_app.task(name="app.workers.tasks.daily_cup.advance_rounds")
def advance_rounds() -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.advance_rounds"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-round-advance",
        awaitable=advance_daily_cup_rounds_async(),
    )


configure_daily_cup_schedule(celery_app)
