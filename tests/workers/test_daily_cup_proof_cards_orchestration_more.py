from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks import daily_cup_proof_cards


class _Bot:
    def __init__(self) -> None:
        self.session = SimpleNamespace(close=self._close)
        self.closed = False

    async def _close(self) -> None:
        self.closed = True


def test_run_daily_cup_proof_cards_async_empty_and_invalid_paths(monkeypatch) -> None:
    assert asyncio.run(
        daily_cup_proof_cards.run_daily_cup_proof_cards_async(tournament_id="bad")
    ) == {
        "processed": 0,
        "participants_total": 0,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }

    async def _none_context(**_kwargs):
        return None

    monkeypatch.setattr(daily_cup_proof_cards, "_load_proof_cards_context", _none_context)
    assert asyncio.run(
        daily_cup_proof_cards.run_daily_cup_proof_cards_async(tournament_id=str(uuid4()))
    ) == {
        "processed": 0,
        "participants_total": 0,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }


def test_run_daily_cup_proof_cards_async_delivers_and_grants_rewards(monkeypatch) -> None:
    tournament_id = uuid4()
    bot = _Bot()
    calls: list[tuple[str, object]] = []
    context = SimpleNamespace(
        participants=[SimpleNamespace(user_id=1)],
        participants_total=99,
    )

    async def _context(**kwargs):
        calls.append(("context", kwargs["user_id"]))
        return context

    async def _deliver(**kwargs):
        calls.append(("deliver", kwargs["bot"]))
        return SimpleNamespace(sent=1, cached_reused=0, failed=0)

    async def _grant(**kwargs):
        calls.append(("grant", kwargs["tournament_id"]))
        return []

    monkeypatch.setattr(daily_cup_proof_cards.asyncio, "sleep", lambda _seconds: _instant_sleep())
    monkeypatch.setattr(daily_cup_proof_cards, "_load_proof_cards_context", _context)
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_proof_cards, "deliver_daily_cup_proof_cards", _deliver)
    monkeypatch.setattr(daily_cup_proof_cards, "_grant_winner_rewards_once", _grant)

    result = asyncio.run(
        daily_cup_proof_cards.run_daily_cup_proof_cards_async(
            tournament_id=str(tournament_id),
            initial_delay_seconds=1,
        )
    )

    assert result == {
        "processed": 1,
        "participants_total": 99,
        "sent": 1,
        "cached_reused": 0,
        "failed": 0,
    }
    assert bot.closed is True
    assert calls == [("context", None), ("deliver", bot), ("grant", str(tournament_id))]


def test_daily_cup_proof_cards_enqueue_and_task_wrapper(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards_job",
        _record_enqueue(calls),
    )
    assert daily_cup_proof_cards.enqueue_daily_cup_proof_cards(
        tournament_id="tid",
        user_id=1,
        delay_seconds=5,
        lock_retry_attempt=2,
    )
    assert calls[0]["tournament_id"] == "tid"
    assert calls[0]["celery_task"] is daily_cup_proof_cards.run_daily_cup_proof_cards


async def _instant_sleep() -> None:
    return None


def _record_enqueue(target: list[dict[str, object]]):
    def _inner(**kwargs) -> bool:
        target.append(kwargs)
        return True

    return _inner
