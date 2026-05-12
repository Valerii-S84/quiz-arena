from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.workers.tasks import tournaments_proof_cards
from app.workers.tasks.tournaments_proof_cards_delivery import (
    TournamentProofCardContext,
    deliver_proof_cards,
)
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


class _Bot:
    def __init__(self) -> None:
        self.session = SimpleNamespace(close=self._close)
        self.closed = False
        self.photos: list[dict[str, object]] = []

    async def _close(self) -> None:
        self.closed = True

    async def send_photo(self, **kwargs):
        self.photos.append(kwargs)
        return SimpleNamespace(photo=[SimpleNamespace(file_id="new")])


def test_tournament_proof_cards_delivery_retries_lock_skips_and_counts_failures() -> None:
    context = TournamentProofCardContext(
        parsed_tournament_id=uuid4(),
        tournament=SimpleNamespace(name="Cup", current_round=2),
        participants=[SimpleNamespace(user_id=1), SimpleNamespace(user_id=2)],
        participants_total=2,
        tournament_format="5 Fragen",
        standings_user_ids=[1, 2],
        points_by_user={1: "7", 2: "3"},
        telegram_targets={1: 10, 2: 20},
        user_labels={1: "Ada", 2: "Bea"},
    )
    bot = _Bot()

    class _Repo:
        async def get_for_tournament_user_for_update(self, *_args, **_kwargs):
            return None

    queued: list[dict[str, object]] = []

    def _queue_retry(**kwargs) -> bool:
        queued.append(kwargs)
        return False

    result = asyncio.run(
        deliver_proof_cards(
            request=tournaments_proof_cards.TournamentProofCardDeliveryRequest(
                context=context,
                tournament_id=str(context.parsed_tournament_id),
                now_utc=datetime.now(timezone.utc),
                explicit_resend=False,
            ),
            services=tournaments_proof_cards.TournamentProofCardDeliveryServices(
                session_factory=session_local_with_sessions("s1", "s2"),
                participants_repo=_Repo(),
                build_bot_fn=lambda: bot,
                build_caption_fn=lambda **_kwargs: "caption",
                render_card_fn=lambda **_kwargs: b"png",
                enqueue_retry_fn=_queue_retry,
                logger=SimpleNamespace(
                    info=lambda *_a, **_k: None,
                    warning=lambda *_a, **_k: None,
                ),
            ),
        )
    )

    assert result.failed == 2
    assert queued[0]["explicit_resend"] is False
    assert bot.closed is True


def test_private_tournament_proof_cards_orchestration_and_enqueue(monkeypatch) -> None:
    tournament_id = uuid4()
    context = SimpleNamespace(participants=[SimpleNamespace(user_id=1)], participants_total=1)
    calls: list[dict[str, Any]] = []

    async def _context(**_kwargs):
        return context

    async def _deliver(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(sent=1, cached_reused=0, failed=0)

    monkeypatch.setattr(
        tournaments_proof_cards, "SessionLocal", session_local_with_sessions("session")
    )
    monkeypatch.setattr(tournaments_proof_cards, "load_proof_card_context", _context)
    monkeypatch.setattr(tournaments_proof_cards, "deliver_proof_cards", _deliver)
    monkeypatch.setattr(tournaments_proof_cards.asyncio, "sleep", lambda _seconds: _sleep_done())

    result = asyncio.run(
        tournaments_proof_cards.run_private_tournament_proof_cards_async(
            tournament_id=str(tournament_id),
            user_id=1,
            initial_delay_seconds=1,
            explicit_resend=True,
        )
    )

    assert result == {
        "processed": 1,
        "participants_total": 1,
        "sent": 1,
        "cached_reused": 0,
        "failed": 0,
    }
    assert calls[0]["request"].explicit_resend is True

    monkeypatch.setattr(
        tournaments_proof_cards,
        "enqueue_private_tournament_proof_cards_job",
        _record_call(calls),
    )
    assert tournaments_proof_cards.enqueue_private_tournament_proof_cards(tournament_id="tid")


async def _sleep_done() -> None:
    return None


def _record_call(target: list[dict[str, Any]]):
    def _inner(**kwargs) -> bool:
        target.append(kwargs)
        return True

    return _inner
