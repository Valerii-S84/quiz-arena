from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.workers.tasks import daily_cup_message_delivery_persistence as daily_persistence
from app.workers.tasks import daily_cup_registration_push as registration_push
from app.workers.tasks import tournaments_messaging_delivery
from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext
from tests.game.tournaments_unit_support import NOW_UTC, tournament_row
from tests.workers.payments_reliability_async_support import SessionLocalStub


async def test_daily_cup_message_and_terminal_cas_share_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions: list[object] = []

    async def _persist(**kwargs) -> None:
        sessions.append(kwargs["session"])

    async def _lost(session, **_kwargs) -> int:
        sessions.append(session)
        return 0

    monkeypatch.setattr(daily_persistence, "persist_standings_message_ids", _persist)
    monkeypatch.setattr(daily_persistence.TelegramDeliveryAttemptsRepo, "mark_sent", _lost)
    monkeypatch.setattr(daily_persistence, "SessionLocal", SessionLocalStub())

    with pytest.raises(RuntimeError, match="terminal lease was lost"):
        await daily_persistence.persist_daily_cup_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="delivery")),
            UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            1,
            SimpleNamespace(message_id=501),
            NOW_UTC,
        )

    assert len(sessions) == 2
    assert sessions[0] is sessions[1]


async def test_daily_cup_message_persistence_failure_skips_terminal_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_calls: list[object] = []

    async def _persist(**_kwargs) -> None:
        raise RuntimeError("persistence failed")

    async def _sent(*_args, **_kwargs) -> int:
        sent_calls.append(object())
        return 1

    monkeypatch.setattr(daily_persistence, "persist_standings_message_ids", _persist)
    monkeypatch.setattr(daily_persistence.TelegramDeliveryAttemptsRepo, "mark_sent", _sent)
    monkeypatch.setattr(daily_persistence, "SessionLocal", SessionLocalStub())

    with pytest.raises(RuntimeError, match="persistence failed"):
        await daily_persistence.persist_daily_cup_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="delivery")),
            UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            1,
            SimpleNamespace(message_id=501),
            NOW_UTC,
        )

    assert sent_calls == []


async def test_daily_cup_fallback_terminal_writes_roll_back_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"message_id": 400, "fallback": "PENDING", "original": "PENDING"}

    class _RollbackContext:
        async def __aenter__(self) -> object:
            self.snapshot = dict(state)
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            if exc_type is not None:
                state.clear()
                state.update(self.snapshot)
            return False

    class _RollbackSessionLocal:
        @staticmethod
        def begin() -> _RollbackContext:
            return _RollbackContext()

    async def _persist(**_kwargs) -> None:
        state["message_id"] = 501

    async def _sent(*_args, **_kwargs) -> int:
        state["fallback"] = "SENT"
        return 1

    async def _skipped(*_args, **_kwargs) -> int:
        raise RuntimeError("failure between terminal writes")

    monkeypatch.setattr(daily_persistence, "persist_standings_message_ids", _persist)
    monkeypatch.setattr(daily_persistence.TelegramDeliveryAttemptsRepo, "mark_sent", _sent)
    monkeypatch.setattr(
        daily_persistence.TelegramDeliveryAttemptsRepo,
        "mark_skipped",
        _skipped,
    )
    monkeypatch.setattr(daily_persistence, "SessionLocal", _RollbackSessionLocal)

    with pytest.raises(RuntimeError, match="failure between terminal writes"):
        await daily_persistence.persist_daily_cup_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="fallback")),
            UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            1,
            SimpleNamespace(message_id=501),
            NOW_UTC,
            replace_existing=True,
            original_target=cast(Any, SimpleNamespace(idempotency_key="original")),
        )

    assert state == {"message_id": 400, "fallback": "PENDING", "original": "PENDING"}


async def test_private_tournament_persistence_failure_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _Bot()
    tournament = tournament_row(status="ROUND_1")
    context = TournamentRoundMessagingContext(
        parsed_tournament_id=tournament.id,
        tournament=tournament,
        standings_user_ids=[1],
        points_by_user={1: "1"},
        place_by_user={1: 1},
        participant_rows={1: SimpleNamespace(standings_message_id=None)},
        telegram_targets={1: 101},
        labels={1: "A"},
        round_matches=[],
    )

    async def _prepare(**kwargs):
        return SimpleNamespace(
            should_send=True,
            idempotency_key=kwargs["target"].idempotency_key,
        )

    async def _dispatch(*_args, **_kwargs) -> None:
        return None

    async def _persist(*_args, **_kwargs) -> int:
        raise RuntimeError("durability unavailable")

    monkeypatch.setattr(tournaments_messaging_delivery, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(
        tournaments_messaging_delivery,
        "begin_telegram_delivery_dispatch",
        _dispatch,
    )
    monkeypatch.setattr(
        tournaments_messaging_delivery,
        "persist_private_tournament_sent_message",
        _persist,
    )

    with pytest.raises(RuntimeError, match="durability unavailable"):
        await tournaments_messaging_delivery.deliver_round_messages(
            context=context,
            build_bot_fn=lambda: bot,
            resolve_match_context_fn=lambda **_kwargs: (None, None),
            build_standings_lines_fn=lambda **_kwargs: ["standings"],
            build_completed_text_fn=lambda **_kwargs: "completed",
            build_round_text_fn=lambda **_kwargs: "round",
            format_deadline_fn=lambda _deadline: "deadline",
            build_keyboard_fn=lambda **_kwargs: "keyboard",
            add_share_button_fn=lambda **kwargs: kwargs["keyboard"],
            build_share_url_fn=lambda **_kwargs: "share",
            is_message_not_modified_error_fn=lambda _exc: False,
            logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        )

    assert bot.closed


@pytest.mark.parametrize("failure_stage", ["outcome", "failed_send"])
async def test_registration_persistence_failures_propagate(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    bot = _Bot(
        send_error=RuntimeError("telegram failed") if failure_stage == "failed_send" else None
    )

    async def _prepare(**kwargs):
        return SimpleNamespace(
            should_send=True,
            idempotency_key=kwargs["target"].idempotency_key,
        )

    async def _dispatch(*_args, **_kwargs) -> None:
        return None

    async def _outcome(*_args, **_kwargs) -> None:
        if failure_stage == "outcome":
            raise RuntimeError("outcome persistence failed")

    async def _failed(*_args, **_kwargs) -> None:
        if failure_stage == "failed_send":
            raise RuntimeError("failure persistence failed")

    monkeypatch.setattr(registration_push, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(registration_push, "begin_telegram_delivery_dispatch", _dispatch)
    monkeypatch.setattr(registration_push, "record_daily_cup_registration_push_sent", _outcome)
    monkeypatch.setattr(registration_push, "mark_telegram_delivery_failed", _failed)

    run = registration_push.DailyCupRegistrationPushRun(
        bot=bot,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        flow="daily_cup_registration_push",
        task_name="daily_cup_registration_push",
        text="text",
        tournament_id_text="cup",
        happened_at=NOW_UTC,
        sent_event_type="daily_cup_registration_push_sent",
    )
    target = registration_push.daily_cup_delivery_target(
        flow=run.flow,
        task_name=run.task_name,
        tournament_id_text=run.tournament_id_text,
        user_id=1,
        telegram_user_id=101,
    )
    with pytest.raises(RuntimeError, match="persistence failed"):
        await registration_push._send_daily_cup_registration_push_once(
            run=run,
            target=target,
            user_id=1,
        )


class _Bot:
    def __init__(self, *, send_error: Exception | None = None) -> None:
        self.send_error = send_error
        self.closed = False
        self.session = SimpleNamespace(close=self._close)

    async def send_message(self, **_kwargs):
        if self.send_error is not None:
            raise self.send_error
        return SimpleNamespace(message_id=501)

    async def edit_message_text(self, **_kwargs) -> None:
        return None

    async def _close(self) -> None:
        self.closed = True
