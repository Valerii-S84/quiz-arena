from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import daily_cup_flow
from app.bot.texts.de import TEXTS_DE
from app.workers.tasks import daily_cup_proof_cards
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_daily_cup_share_result_sends_inline_share_and_enqueues_card(
    monkeypatch,
) -> None:
    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=101)

    async def _fake_get_lobby(session, *, tournament_id, viewer_user_id):
        del session, tournament_id, viewer_user_id
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                status="COMPLETED",
            ),
            viewer_joined=True,
            participants=(
                SimpleNamespace(user_id=101, score=Decimal("3.0"), tie_break=Decimal("9.0")),
                SimpleNamespace(user_id=202, score=Decimal("2.0"), tie_break=Decimal("4.5")),
            ),
        )

    emitted: list[str] = []
    enqueued: list[tuple[str, int | None, int]] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(kwargs["event_type"])

    def _fake_enqueue(*, tournament_id: str, user_id: int | None = None, delay_seconds: int = 2):
        enqueued.append((tournament_id, user_id, delay_seconds))

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards",
        _fake_enqueue,
    )

    callback = DummyCallback(
        data="daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )

    await daily_cup_flow.handle_daily_cup_share_result(
        callback,
        tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        tournament_service=SimpleNamespace(get_daily_cup_lobby_by_id=_fake_get_lobby),
        emit_analytics_event=_fake_emit,
        event_source_bot="telegram",
    )

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.daily_cup.share.ready"]
    inline_queries = [
        button.switch_inline_query
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.switch_inline_query
    ]
    assert inline_queries == ["proof:daily:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
    assert emitted == ["daily_cup_result_shared"]
    assert enqueued == [("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 101, 0)]


@pytest.mark.asyncio
async def test_handle_daily_cup_request_proof_card_enqueues_card(monkeypatch) -> None:
    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=101)

    async def _fake_get_lobby(session, *, tournament_id, viewer_user_id):
        del session, tournament_id, viewer_user_id
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                status="COMPLETED",
            ),
            viewer_joined=True,
            participants=(SimpleNamespace(user_id=101, score=Decimal("3.0")),),
        )

    emitted: list[str] = []
    enqueued: list[tuple[str, int | None, int]] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(kwargs["event_type"])

    def _fake_enqueue(*, tournament_id: str, user_id: int | None = None, delay_seconds: int = 2):
        enqueued.append((tournament_id, user_id, delay_seconds))

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards",
        _fake_enqueue,
    )

    callback = DummyCallback(
        data="daily:cup:proof:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )

    await daily_cup_flow.handle_daily_cup_request_proof_card(
        callback,
        tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        tournament_service=SimpleNamespace(get_daily_cup_lobby_by_id=_fake_get_lobby),
        emit_analytics_event=_fake_emit,
        event_source_bot="telegram",
    )

    assert emitted == ["daily_cup_proof_card_requested"]
    assert enqueued == [("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 101, 0)]
    assert callback.answer_calls == [
        {"text": TEXTS_DE["msg.daily_cup.proof_card.queued"], "show_alert": False}
    ]


@pytest.mark.asyncio
async def test_handle_daily_cup_view_shows_active_standings() -> None:
    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=101)

    async def _fake_get_lobby(session, *, tournament_id, viewer_user_id):
        del session, tournament_id, viewer_user_id
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                status="ROUND_2",
                current_round=2,
                round_deadline=None,
            ),
            viewer_joined=True,
            viewer_current_match_challenge_id=None,
            viewer_current_opponent_user_id=None,
            participants=(
                SimpleNamespace(user_id=101, score=Decimal("2.0"), tie_break=Decimal("5.0")),
                SimpleNamespace(user_id=202, score=Decimal("1.0"), tie_break=Decimal("3.0")),
            ),
        )

    async def _fake_list_by_ids(session, user_ids):
        del session
        return [
            SimpleNamespace(
                id=user_id, username=None, first_name=("Ich" if user_id == 101 else "Max")
            )
            for user_id in user_ids
        ]

    async def _fake_emit(*args, **kwargs):
        return None

    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )

    await daily_cup_flow.handle_daily_cup_view(
        callback,
        tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        tournament_service=SimpleNamespace(get_daily_cup_lobby_by_id=_fake_get_lobby),
        users_repo=SimpleNamespace(list_by_ids=_fake_list_by_ids),
        emit_analytics_event=_fake_emit,
        event_source_bot="telegram",
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Runde 2/4" in text
    assert "1. 🥇 Ich (Du) - 2 Pkt" in text
    assert "2. 🥈 Max - 1 Pkt" in text


@pytest.mark.asyncio
async def test_handle_daily_cup_view_shows_completed_final_table_and_emits_event() -> None:
    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=101)

    async def _fake_get_lobby(session, *, tournament_id, viewer_user_id):
        del session, tournament_id, viewer_user_id
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                status="COMPLETED",
                current_round=4,
                round_deadline=None,
            ),
            viewer_joined=True,
            viewer_current_match_challenge_id=None,
            viewer_current_opponent_user_id=None,
            participants=(
                SimpleNamespace(user_id=101, score=Decimal("3.0"), tie_break=Decimal("9.0")),
                SimpleNamespace(user_id=202, score=Decimal("2.0"), tie_break=Decimal("4.5")),
            ),
        )

    async def _fake_list_by_ids(session, user_ids):
        del session
        return [
            SimpleNamespace(
                id=user_id, username=None, first_name=("Ich" if user_id == 101 else "Max")
            )
            for user_id in user_ids
        ]

    emitted: list[str] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(kwargs["event_type"])

    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )

    await daily_cup_flow.handle_daily_cup_view(
        callback,
        tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        tournament_service=SimpleNamespace(get_daily_cup_lobby_by_id=_fake_get_lobby),
        users_repo=SimpleNamespace(list_by_ids=_fake_list_by_ids),
        emit_analytics_event=_fake_emit,
        event_source_bot="telegram",
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Daily Arena Cup — Abgeschlossen!" in text
    assert "📊 Endtabelle" in text
    assert "TB 9" in text
    assert emitted == ["daily_cup_final_viewed"]
