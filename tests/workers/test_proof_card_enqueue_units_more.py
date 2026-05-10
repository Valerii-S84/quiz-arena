from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from app.workers.tasks.daily_cup_proof_cards_enqueue import enqueue_daily_cup_proof_cards_job
from app.workers.tasks.tournaments_proof_cards_enqueue import (
    enqueue_private_tournament_proof_cards_job,
)


async def _noop_async(**_kwargs):
    return None


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **kwargs) -> None:
        self.warnings.append((event, kwargs))


def test_daily_cup_enqueue_uses_celery_kwargs_and_clamps_countdown() -> None:
    calls: list[dict[str, object]] = []
    task = SimpleNamespace(apply_async=lambda **kwargs: calls.append(kwargs))

    result = enqueue_daily_cup_proof_cards_job(
        tournament_id="tid",
        user_id=3,
        delay_seconds=-10,
        lock_retry_attempt=2,
        celery_task=task,
        async_fn=_noop_async,
        is_celery_task_fn=lambda _task: True,
        run_async_job_fn=lambda _coro: None,
        logger=_Logger(),
    )

    assert result is True
    assert calls == [
        {
            "kwargs": {
                "tournament_id": "tid",
                "user_id": 3,
                "initial_delay_seconds": 0,
                "lock_retry_attempt": 2,
            },
            "countdown": 0,
        }
    ]


def test_daily_cup_enqueue_fallback_closes_coroutine_and_logs_failures() -> None:
    logger = _Logger()
    coros: list[object] = []

    def _run(coro) -> None:
        coros.append(coro)
        coro.close()

    assert enqueue_daily_cup_proof_cards_job(
        tournament_id="tid",
        user_id=None,
        delay_seconds=5,
        celery_task=object(),
        async_fn=_noop_async,
        is_celery_task_fn=lambda _task: False,
        run_async_job_fn=_run,
        logger=logger,
    )
    assert len(coros) == 1

    result = enqueue_daily_cup_proof_cards_job(
        tournament_id="tid",
        user_id=1,
        delay_seconds=0,
        lock_retry_attempt=4,
        celery_task=object(),
        async_fn=_noop_async,
        is_celery_task_fn=lambda _task: False,
        run_async_job_fn=_run,
        logger=logger,
    )

    assert result is False
    assert logger.warnings[-1][0] == "daily_cup_proof_card_retry_exhausted"


def test_private_enqueue_preserves_explicit_resend_and_handles_apply_errors() -> None:
    logger = _Logger()

    class _Task:
        def apply_async(self, **_kwargs) -> None:
            raise RuntimeError("queue down")

    failed = enqueue_private_tournament_proof_cards_job(
        tournament_id="tid",
        user_id=2,
        explicit_resend=True,
        delay_seconds=1,
        celery_task=_Task(),
        async_fn=_noop_async,
        is_celery_task_fn=lambda _task: True,
        run_async_job_fn=lambda _coro: None,
        logger=logger,
    )

    assert failed is False
    assert logger.warnings[-1][0] == "private_tournament_proof_card_enqueue_failed"

    calls: list[dict[str, object]] = []
    assert enqueue_private_tournament_proof_cards_job(
        tournament_id="tid",
        user_id=None,
        explicit_resend=True,
        delay_seconds=3,
        celery_task=SimpleNamespace(apply_async=lambda **kwargs: calls.append(kwargs)),
        async_fn=_noop_async,
        is_celery_task_fn=lambda _task: True,
        run_async_job_fn=lambda _coro: None,
        logger=logger,
    )
    task_kwargs = cast(dict[str, Any], calls[0]["kwargs"])
    assert task_kwargs["explicit_resend"] is True
