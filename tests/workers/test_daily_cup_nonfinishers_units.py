from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_nonfinishers_summary as summary
from app.workers.tasks import daily_cup_nonfinishers_summary_context as context_mod
from tests.workers.payments_reliability_async_support import SessionLocalStub


def test_collect_nonfinishers_and_user_finish_state() -> None:
    challenge_id = uuid4()
    challenge = cast(
        Any,
        SimpleNamespace(
            id=challenge_id,
            total_rounds=3,
            creator_user_id=11,
            creator_finished_at=None,
            creator_answered_round=2,
            opponent_user_id=22,
            opponent_finished_at=object(),
            opponent_answered_round=1,
        ),
    )
    matches = [SimpleNamespace(friend_challenge_id=challenge_id, user_a=11, user_b=22)]

    assert context_mod.user_did_not_finish_challenge(challenge=challenge, user_id=11)
    assert not context_mod.user_did_not_finish_challenge(challenge=challenge, user_id=22)
    assert not context_mod.user_did_not_finish_challenge(challenge=challenge, user_id=33)
    assert context_mod.collect_nonfinishers(
        matches=matches, challenges_by_id={challenge_id: challenge}
    ) == {11}


@pytest.mark.asyncio
async def test_run_daily_cup_nonfinishers_summary_async_delivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = SimpleNamespace(session=SimpleNamespace(close=_async_return(None)))
    delivery = SimpleNamespace(sent=1, failed=1)
    monkeypatch.setattr(summary, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        summary,
        "load_daily_cup_nonfinishers_summary_context",
        _async_return(
            SimpleNamespace(
                participants_total=3,
                nonfinishers=[11, 22],
                telegram_targets={11: 101, 22: 102},
            )
        ),
    )
    monkeypatch.setattr(summary, "build_bot", lambda: bot)
    monkeypatch.setattr(summary, "deliver_daily_cup_nonfinishers_summary", _async_return(delivery))

    result = await summary.run_daily_cup_nonfinishers_summary_async(tournament_id=str(uuid4()))

    assert result == {
        "processed": 1,
        "participants_total": 3,
        "nonfinishers_total": 2,
        "sent": 1,
        "failed": 1,
    }


@pytest.mark.asyncio
async def test_run_daily_cup_nonfinishers_summary_async_empty_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await summary.run_daily_cup_nonfinishers_summary_async(tournament_id="bad") == {
        "processed": 0,
        "participants_total": 0,
        "nonfinishers_total": 0,
        "sent": 0,
        "failed": 0,
    }

    monkeypatch.setattr(summary, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(summary, "load_daily_cup_nonfinishers_summary_context", _async_return(None))
    assert await summary.run_daily_cup_nonfinishers_summary_async(tournament_id=str(uuid4())) == {
        "processed": 0,
        "participants_total": 0,
        "nonfinishers_total": 0,
        "sent": 0,
        "failed": 0,
    }


def test_enqueue_daily_cup_nonfinishers_summary_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs: list[object] = []
    monkeypatch.setattr(summary, "_is_celery_task", lambda _task: False)
    monkeypatch.setattr(summary, "run_async_job", _record_and_close(jobs))

    summary.enqueue_daily_cup_nonfinishers_summary(tournament_id=str(uuid4()), delay_seconds=1)

    assert jobs


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _record_and_close(target: list[object]):
    def _inner(coro) -> None:
        target.append(coro)
        coro.close()

    return _inner
