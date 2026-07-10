from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.workers.tasks import tournaments_messaging, tournaments_proof_cards
from app.workers.tasks.tournaments_messaging_delivery import TournamentRoundDeliveryResult
from tests.game.tournaments_unit_support import tournament_row
from tests.workers.payments_reliability_async_support import SessionLocalStub


def test_tournament_messaging_helpers_and_enqueue_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs: list[object] = []
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="top", callback_data="top")],
            [InlineKeyboardButton(text="bottom", callback_data="bottom")],
        ]
    )
    monkeypatch.setattr(tournaments_messaging, "public_bot_start_link", lambda **_kwargs: "start")
    monkeypatch.setattr(
        tournaments_messaging, "build_tournament_share_url", lambda **_kwargs: "share"
    )
    monkeypatch.setattr(tournaments_messaging, "run_async_job", _record_and_close(jobs))
    monkeypatch.setattr(tournaments_messaging, "_is_celery_task", lambda _task: False)

    assert not tournaments_messaging._is_celery_task(object())
    assert (
        tournaments_messaging._build_standings_share_url(
            invite_code="abc",
            tournament_name=None,
        )
        == "share"
    )
    assert (
        len(
            tournaments_messaging._with_standings_share_button(
                keyboard=keyboard,
                share_url="share",
            ).inline_keyboard
        )
        == 3
    )

    tournaments_messaging.enqueue_private_tournament_round_messaging(tournament_id=str(uuid4()))
    assert jobs


@pytest.mark.asyncio
async def test_run_private_tournament_round_messaging_async_persists_sent_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = uuid4()
    context = SimpleNamespace(
        standings_user_ids=[11, 22],
        parsed_tournament_id=tournament_id,
    )
    persisted: list[dict[str, object]] = []

    monkeypatch.setattr(tournaments_messaging, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        tournaments_messaging, "load_round_messaging_context", _async_return(context)
    )
    monkeypatch.setattr(
        tournaments_messaging,
        "deliver_round_messages",
        _async_return(TournamentRoundDeliveryResult(1, 2, 0, 0, {11: 101}, {22: 202})),
    )

    async def _persist(**kwargs) -> None:
        persisted.append(kwargs)

    monkeypatch.setattr(tournaments_messaging, "persist_standings_message_ids", _persist)

    result = await tournaments_messaging.run_private_tournament_round_messaging_async(
        tournament_id=str(tournament_id),
    )

    assert result == {
        "processed": 1,
        "participants_total": 2,
        "sent": 1,
        "edited": 2,
        "failed": 0,
        "skipped": 0,
    }
    assert persisted[0]["new_message_ids"] == {11: 101}


@pytest.mark.asyncio
async def test_tournament_proof_cards_helpers_and_async_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = uuid4()
    context = SimpleNamespace(participants=[object()], participants_total=1)
    monkeypatch.setattr(tournaments_proof_cards, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(tournaments_proof_cards, "load_proof_card_context", _async_return(context))
    monkeypatch.setattr(tournaments_proof_cards.asyncio, "sleep", _async_return(None))
    monkeypatch.setattr(
        tournaments_proof_cards,
        "deliver_proof_cards",
        _async_return(SimpleNamespace(sent=1, cached_reused=0, failed=0)),
    )

    assert tournaments_proof_cards._format_user_label(username=" user ", first_name=None) == "@user"
    assert tournaments_proof_cards._format_user_label(username=None, first_name=" Name ") == "Name"
    assert tournaments_proof_cards._format_user_label(username=None, first_name=None) == "Spieler"
    assert tournaments_proof_cards._format_tournament_format("QUICK_12") == "12 Fragen"
    assert tournaments_proof_cards._build_caption(place=1, points="3") == (
        "🏆 Turnier abgeschlossen\nPlatz #1\nPunkte: 3"
    )
    assert tournaments_proof_cards._build_proof_card_result(
        processed=0,
        participants_total=0,
    ) == {
        "processed": 0,
        "participants_total": 0,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }
    assert await tournaments_proof_cards.run_private_tournament_proof_cards_async(
        tournament_id="bad-id",
    ) == tournaments_proof_cards._build_proof_card_result(processed=0, participants_total=0)
    assert await tournaments_proof_cards.run_private_tournament_proof_cards_async(
        tournament_id=str(tournament_id),
        user_id=11,
        explicit_resend=True,
        initial_delay_seconds=1,
    ) == {
        "processed": 1,
        "participants_total": 1,
        "sent": 1,
        "cached_reused": 0,
        "failed": 0,
    }


def test_tournament_proof_cards_enqueue_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def _enqueue_job(**kwargs: object) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(
        tournaments_proof_cards,
        "enqueue_private_tournament_proof_cards_job",
        _enqueue_job,
    )

    assert tournaments_proof_cards.enqueue_private_tournament_proof_cards(
        tournament_id=str(tournament_row().id),
        user_id=11,
    )
    assert calls[0]["user_id"] == 11


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _record_and_close(target: list[object]):
    def _inner(coro) -> None:
        target.append(coro)
        coro.close()

    return _inner
