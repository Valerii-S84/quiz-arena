from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers.tasks import tournaments_proof_cards
from tests.game.daily_arena_golden_support import (
    DummyBot,
    async_return,
    close_coroutine_and_raise,
    close_coroutine_with_name,
    session_local_with_sessions,
)


def test_private_tournament_proof_cards_enqueue_paths_and_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: dict[str, object] = {}

    monkeypatch.setattr(
        tournaments_proof_cards,
        "_is_celery_task",
        lambda task: task is tournaments_proof_cards.run_private_tournament_proof_cards,
    )
    monkeypatch.setattr(
        tournaments_proof_cards.run_private_tournament_proof_cards,
        "apply_async",
        lambda **kwargs: enqueued.setdefault("apply_async", kwargs),
    )
    assert tournaments_proof_cards.enqueue_private_tournament_proof_cards(
        tournament_id="private-proof",
        user_id=7,
        explicit_resend=True,
        delay_seconds=3,
    )
    assert enqueued["apply_async"] == {
        "kwargs": {
            "tournament_id": "private-proof",
            "user_id": 7,
            "initial_delay_seconds": 0,
            "explicit_resend": True,
        },
        "countdown": 3,
    }

    monkeypatch.setattr(tournaments_proof_cards, "_is_celery_task", lambda task: False)
    monkeypatch.setattr(
        tournaments_proof_cards,
        "run_async_job",
        lambda coroutine: enqueued.setdefault(
            "run_async_job", close_coroutine_with_name(coroutine)
        ),
    )
    assert tournaments_proof_cards.enqueue_private_tournament_proof_cards(
        tournament_id="private-proof-async",
        delay_seconds=4,
    )
    assert enqueued["run_async_job"] == "run_private_tournament_proof_cards_async"

    warnings: list[dict[str, object]] = []
    monkeypatch.setattr(
        tournaments_proof_cards,
        "run_async_job",
        lambda coroutine: close_coroutine_and_raise(coroutine, RuntimeError("boom")),
    )
    monkeypatch.setattr(
        tournaments_proof_cards.logger,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )
    assert (
        tournaments_proof_cards.enqueue_private_tournament_proof_cards(
            tournament_id="private-proof-failed",
            user_id=11,
        )
        is False
    )
    assert warnings == [
        {
            "event": "private_tournament_proof_card_enqueue_failed",
            "tournament_id": "private-proof-failed",
            "user_id": 11,
            "error_type": "RuntimeError",
        }
    ]

    monkeypatch.setattr(
        tournaments_proof_cards,
        "run_async_job",
        lambda coroutine: {"wrapped": close_coroutine_with_name(coroutine)},
    )
    wrapped = tournaments_proof_cards.run_private_tournament_proof_cards(
        tournament_id="private-proof-wrapper"
    )
    assert wrapped == {"wrapped": "run_private_tournament_proof_cards_async"}


@pytest.mark.asyncio
async def test_private_tournament_proof_cards_queue_retry_when_participant_row_lock_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = tournaments_proof_cards.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    queued: list[dict[str, object]] = []
    infos: list[dict[str, object]] = []
    bot = DummyBot()
    context = SimpleNamespace(
        parsed_tournament_id=tournament_id,
        participants=[SimpleNamespace(user_id=101)],
        participants_total=1,
        tournament_format="12 Fragen",
        tournament=SimpleNamespace(name="Freunde", current_round=3),
        standings_user_ids=[101],
        points_by_user={101: "7"},
        telegram_targets={101: 900101},
        user_labels={101: "Spieler"},
    )

    def _fake_enqueue_retry(**kwargs: object) -> bool:
        queued.append(dict(kwargs))
        return True

    monkeypatch.setattr(
        tournaments_proof_cards,
        "load_proof_card_context",
        async_return(context),
    )
    monkeypatch.setattr(tournaments_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(
        tournaments_proof_cards,
        "enqueue_private_tournament_proof_cards",
        _fake_enqueue_retry,
    )
    monkeypatch.setattr(
        tournaments_proof_cards.TournamentParticipantsRepo,
        "get_for_tournament_user_for_update",
        async_return(None),
    )
    monkeypatch.setattr(
        tournaments_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        tournaments_proof_cards.logger,
        "info",
        lambda event, **kwargs: infos.append({"event": event, **kwargs}),
    )

    result = await tournaments_proof_cards.run_private_tournament_proof_cards_async(
        tournament_id=str(tournament_id)
    )

    assert result == {
        "processed": 1,
        "participants_total": 1,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }
    assert queued == [
        {
            "tournament_id": str(tournament_id),
            "user_id": 101,
            "explicit_resend": False,
            "delay_seconds": 2,
            "lock_retry_attempt": 1,
        }
    ]
    assert infos == [
        {
            "event": "private_tournament_proof_card_retry_queued",
            "tournament_id": str(tournament_id),
            "user_id": 101,
            "retry_attempt": 1,
            "reason": "participant_row_lock_skipped",
        }
    ]
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_private_tournament_proof_cards_mark_failed_when_lock_skip_retry_is_not_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = tournaments_proof_cards.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    bot = DummyBot()
    context = SimpleNamespace(
        parsed_tournament_id=tournament_id,
        participants=[SimpleNamespace(user_id=101)],
        participants_total=1,
        tournament_format="12 Fragen",
        tournament=SimpleNamespace(name="Freunde", current_round=3),
        standings_user_ids=[101],
        points_by_user={101: "7"},
        telegram_targets={101: 900101},
        user_labels={101: "Spieler"},
    )

    monkeypatch.setattr(
        tournaments_proof_cards,
        "load_proof_card_context",
        async_return(context),
    )
    monkeypatch.setattr(tournaments_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(
        tournaments_proof_cards,
        "enqueue_private_tournament_proof_cards",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        tournaments_proof_cards.TournamentParticipantsRepo,
        "get_for_tournament_user_for_update",
        async_return(None),
    )
    monkeypatch.setattr(
        tournaments_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace(), SimpleNamespace()),
    )

    result = await tournaments_proof_cards.run_private_tournament_proof_cards_async(
        tournament_id=str(tournament_id)
    )

    assert result == {
        "processed": 1,
        "participants_total": 1,
        "sent": 0,
        "cached_reused": 0,
        "failed": 1,
    }
    assert bot.session.closed is True
