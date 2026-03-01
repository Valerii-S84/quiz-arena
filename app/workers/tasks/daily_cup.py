from __future__ import annotations

from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.daily_cup_async import (
    close_daily_cup_registration_and_start_async as _close_daily_cup_registration_and_start_async,
)
from app.workers.tasks.daily_cup_async import (
    open_daily_cup_registration_async as _open_daily_cup_registration_async,
)
from app.workers.tasks.daily_cup_messaging import run_daily_cup_round_messaging
from app.workers.tasks.daily_cup_proof_cards import run_daily_cup_proof_cards
from app.workers.tasks.daily_cup_rounds import (
    advance_daily_cup_rounds_async as _advance_daily_cup_rounds_async,
)
from app.workers.tasks.daily_cup_schedule import configure_daily_cup_schedule

open_daily_cup_registration_async = _open_daily_cup_registration_async
close_daily_cup_registration_and_start_async = _close_daily_cup_registration_and_start_async
advance_daily_cup_rounds_async = _advance_daily_cup_rounds_async

__all__ = [
    "advance_rounds",
    "advance_daily_cup_rounds_async",
    "close_daily_cup_registration_and_start_async",
    "close_registration_and_start",
    "open_daily_cup_registration_async",
    "open_registration",
    "run_daily_cup_proof_cards",
    "run_daily_cup_round_messaging",
]


@celery_app.task(name="app.workers.tasks.daily_cup.open_registration")
def open_registration() -> dict[str, int]:
    return run_async_job(open_daily_cup_registration_async())


@celery_app.task(name="app.workers.tasks.daily_cup.close_registration_and_start")
def close_registration_and_start() -> dict[str, int]:
    return run_async_job(close_daily_cup_registration_and_start_async())


@celery_app.task(name="app.workers.tasks.daily_cup.advance_rounds")
def advance_rounds() -> dict[str, int]:
    return run_async_job(advance_daily_cup_rounds_async())


configure_daily_cup_schedule(celery_app)
