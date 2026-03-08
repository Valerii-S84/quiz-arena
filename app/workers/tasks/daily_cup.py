from __future__ import annotations

from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.daily_cup_async import (
    close_daily_cup_registration_and_start_async as _close_daily_cup_registration_and_start_async,
)
from app.workers.tasks.daily_cup_async import (
    open_daily_cup_registration_async as _open_daily_cup_registration_async,
)
from app.workers.tasks.daily_cup_async import (
    send_daily_cup_invite_async as _send_daily_cup_invite_async,
)
from app.workers.tasks.daily_cup_async import (
    send_daily_cup_last_call_reminder_async as _send_daily_cup_last_call_reminder_async,
)
from app.workers.tasks.daily_cup_async import (
    publish_daily_cup_final_results_async as _publish_daily_cup_final_results_async,
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
from app.workers.tasks.daily_elimination_async import (
    run_daily_elimination_final_deadline_async as _run_daily_elimination_final_deadline_async,
)
from app.workers.tasks.daily_elimination_async import (
    run_elimination_match_timeout_async as _run_elimination_match_timeout_async,
)

open_daily_cup_registration_async = _open_daily_cup_registration_async
close_daily_cup_registration_and_start_async = _close_daily_cup_registration_and_start_async
advance_daily_cup_rounds_async = _advance_daily_cup_rounds_async
send_daily_cup_invite_async = _send_daily_cup_invite_async
send_daily_cup_last_call_reminder_async = _send_daily_cup_last_call_reminder_async
publish_daily_cup_final_results_async = _publish_daily_cup_final_results_async
send_daily_cup_prestart_reminder_async = _send_daily_cup_prestart_reminder_async
run_daily_cup_turn_reminders_async = _run_daily_cup_turn_reminders_async
run_elimination_match_timeout_async = _run_elimination_match_timeout_async
run_daily_elimination_final_deadline_async = _run_daily_elimination_final_deadline_async

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
    "run_daily_elimination_final_deadline",
    "run_elimination_match_timeout",
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
    return run_async_job(send_daily_cup_invite_async())


@celery_app.task(name="app.workers.tasks.daily_cup.open_registration")
def open_registration() -> dict[str, int]:
    return run_async_job(open_daily_cup_registration_async())


@celery_app.task(name="app.workers.tasks.daily_cup.send_last_call_reminder")
def send_last_call_reminder() -> dict[str, int]:
    return run_async_job(send_daily_cup_last_call_reminder_async())


@celery_app.task(name="app.workers.tasks.daily_cup.send_prestart_reminder")
def send_prestart_reminder() -> dict[str, int]:
    return run_async_job(send_daily_cup_prestart_reminder_async())


@celery_app.task(name="app.workers.tasks.daily_cup.publish_final_results")
def publish_final_results() -> dict[str, int]:
    return run_async_job(publish_daily_cup_final_results_async())


@celery_app.task(name="app.workers.tasks.daily_cup.send_turn_reminders")
def send_turn_reminders() -> dict[str, int]:
    return run_async_job(run_daily_cup_turn_reminders_async())


@celery_app.task(name="app.workers.tasks.daily_cup.close_registration_and_start")
def close_registration_and_start() -> dict[str, int]:
    return run_async_job(close_daily_cup_registration_and_start_async())


@celery_app.task(name="app.workers.tasks.daily_cup.advance_rounds")
def advance_rounds() -> dict[str, int]:
    return run_async_job(advance_daily_cup_rounds_async())


@celery_app.task(name="app.workers.tasks.daily_cup.match_timeout")
def run_elimination_match_timeout(match_id: str) -> dict[str, int]:
    return run_async_job(run_elimination_match_timeout_async(match_id=match_id))


@celery_app.task(name="app.workers.tasks.daily_cup.final_deadline")
def run_daily_elimination_final_deadline() -> dict[str, int]:
    return run_async_job(run_daily_elimination_final_deadline_async())


configure_daily_cup_schedule(celery_app)
