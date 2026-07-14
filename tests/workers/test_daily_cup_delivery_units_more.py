from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_messaging_delivery_runtime as daily_runtime
from app.workers.tasks import daily_cup_registration_push_delivery as registration_delivery
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


@pytest.mark.asyncio
async def test_daily_delivery_continues_after_recipient_system_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processed_user_ids: list[int] = []

    async def _deliver(_context, _dependencies, _state, _run, user_id: int) -> None:
        processed_user_ids.append(user_id)
        if user_id == 2:
            raise RuntimeError("daily persistence failed")

    monkeypatch.setattr(daily_runtime, "_deliver_to_user", _deliver)
    context = cast(
        Any,
        SimpleNamespace(
            standings_user_ids=[1, 2, 3],
            participants_total=3,
            tournament=SimpleNamespace(id="cup-1", status="ROUND_1", current_round=1),
        ),
    )
    dependencies = cast(
        Any,
        SimpleNamespace(
            daily_cup_max_rounds_for_participants=lambda **_kwargs: 3,
            happened_at=lambda: datetime(2026, 7, 13, tzinfo=timezone.utc),
            daily_cup_content_version=lambda **_kwargs: "round:1",
        ),
    )

    with pytest.raises(RuntimeError, match="daily persistence failed"):
        await daily_runtime.deliver_daily_cup_messages_with_dependencies(
            context=context,
            dependencies=dependencies,
        )

    assert processed_user_ids == [1, 2, 3]


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


@pytest.mark.asyncio
async def test_registration_payload_failure_happens_before_pending_claim() -> None:
    call_order: list[str] = []

    def _keyboard(**_kwargs: Any) -> object:
        call_order.append("payload")
        raise RuntimeError("payload failed")

    async def _prepare(**_kwargs: Any) -> object:
        call_order.append("prepare")
        return SimpleNamespace(should_send=False)

    run = registration_delivery.DailyCupRegistrationPushRun(
        bot=SimpleNamespace(),
        logger=SimpleNamespace(),
        flow="daily_cup_registration",
        task_name="daily_cup.registration",
        text="text",
        tournament_id_text="cup-1",
        happened_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        sent_event_type="daily_cup_registration_sent",
    )
    operations = registration_delivery.DailyCupRegistrationPushOperations(
        prepare_delivery=_prepare,
        begin_dispatch=None,
        mark_failed=None,
        record_sent=None,
        build_keyboard=_keyboard,
    )

    with pytest.raises(RuntimeError, match="payload failed"):
        await registration_delivery.send_daily_cup_registration_push_once(
            run=run,
            target=cast(Any, SimpleNamespace(chat_id=101)),
            user_id=11,
            operations=operations,
        )

    assert call_order == ["payload"]
