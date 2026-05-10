from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks.daily_cup_nonfinishers_summary_delivery import (
    deliver_daily_cup_nonfinishers_summary,
)
from app.workers.tasks.daily_cup_proof_cards_delivery import deliver_daily_cup_proof_cards
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


class _ParticipantsRepo:
    def __init__(self, rows: list[object | None]) -> None:
        self.rows = list(rows)
        self.sent: list[int] = []
        self.file_ids: list[str] = []

    async def get_for_tournament_user_for_update(self, *_args, **_kwargs):
        return self.rows.pop(0)

    async def set_proof_card_sent(self, _session, **kwargs) -> None:
        self.sent.append(kwargs["user_id"])

    async def set_proof_card_file_id_if_missing(self, _session, **kwargs) -> None:
        self.file_ids.append(kwargs["file_id"])


def test_deliver_daily_cup_proof_cards_counts_success_missing_and_lock_retry() -> None:
    tournament_uuid = uuid4()
    context = SimpleNamespace(
        parsed_tournament_id=tournament_uuid,
        participants=[
            SimpleNamespace(user_id=1),
            SimpleNamespace(user_id=2),
            SimpleNamespace(user_id=3),
        ],
        telegram_targets={1: 10, 3: 30},
        standings_user_ids=[1, 2, 3],
        points_by_user={1: "9", 3: "1"},
        participants_total=3,
        user_labels={1: "Ada", 3: "Bea"},
        rounds_played=2,
    )
    repo = _ParticipantsRepo(
        [SimpleNamespace(proof_card_sent=False, proof_card_file_id=None), None]
    )
    queued: list[dict[str, object]] = []

    def _queue_retry(**kwargs) -> bool:
        queued.append(kwargs)
        return True

    async def _send(**kwargs):
        assert kwargs["place"] == 1
        return True, False, "file-1"

    result = asyncio.run(
        deliver_daily_cup_proof_cards(
            context=context,
            bot=object(),
            tournament_id=str(tournament_uuid),
            now_utc=datetime.now(timezone.utc),
            session_factory=session_local_with_sessions("s1", "s2"),
            participants_repo=repo,
            send_proof_card_fn=_send,
            enqueue_retry_fn=_queue_retry,
            lock_retry_attempt=1,
            render_card_png=lambda **_kwargs: b"png",
            logger=SimpleNamespace(
                info=lambda *_args, **_kwargs: None, warning=lambda *_a, **_k: None
            ),
        )
    )

    assert result.sent == 1
    assert result.failed == 1
    assert repo.sent == [1]
    assert repo.file_ids == ["file-1"]
    assert queued[0]["user_id"] == 3
    assert queued[0]["lock_retry_attempt"] == 2


def test_deliver_daily_cup_nonfinishers_summary_counts_send_failures() -> None:
    class _Bot:
        async def send_message(self, **kwargs) -> None:
            if kwargs["chat_id"] == 20:
                raise RuntimeError("blocked")

    result = asyncio.run(
        deliver_daily_cup_nonfinishers_summary(
            bot=_Bot(),
            nonfinishers=[1, 2, 3],
            telegram_targets={1: 10, 2: 20},
            text="summary",
        )
    )

    assert result.sent == 1
    assert result.failed == 2
