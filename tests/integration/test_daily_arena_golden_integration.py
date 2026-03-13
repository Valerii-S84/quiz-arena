from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_TYPE_DAILY_ARENA, TOURNAMENT_TYPE_PRIVATE
from app.game.tournaments.create_join import join_daily_cup_by_id
from app.game.tournaments.errors import TournamentAccessError, TournamentClosedError
from app.game.tournaments.queries import get_daily_cup_lobby_by_id
from app.workers.tasks import daily_cup_messaging, daily_cup_proof_cards
from tests.game.daily_arena_golden_support import (
    DummyBot,
    create_completed_daily_arena,
    create_daily_tournament,
    create_user,
    create_users,
    prepare_tournament_db,
)


@pytest.mark.asyncio
async def test_daily_arena_join_does_not_raise_for_valid_data() -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_id = await create_user("golden_daily_arena_join")
    tournament_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        result = await join_daily_cup_by_id(
            session,
            user_id=user_id,
            tournament_id=tournament_id,
            now_utc=now_utc,
        )

    assert result.joined_now is True
    assert result.snapshot.type == TOURNAMENT_TYPE_DAILY_ARENA


@pytest.mark.asyncio
async def test_daily_arena_lobby_query_returns_only_daily_arena_tournaments() -> None:
    # GOLDEN: оновлено після видалення Elimination (крок 8)
    # Lobby query ізольована від інших типів турнірів
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await prepare_tournament_db()
    viewer_user_id = await create_user("golden_daily_arena_lobby")
    arena_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        now_utc=now_utc,
    )
    private_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_PRIVATE,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        arena_lobby = await get_daily_cup_lobby_by_id(
            session, tournament_id=arena_id, viewer_user_id=viewer_user_id
        )
        with pytest.raises(TournamentAccessError):
            await get_daily_cup_lobby_by_id(
                session,
                tournament_id=private_id,
                viewer_user_id=viewer_user_id,
            )

    assert arena_lobby.tournament.type == TOURNAMENT_TYPE_DAILY_ARENA


@pytest.mark.asyncio
async def test_daily_arena_join_raises_when_registration_is_already_closed() -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_id = await create_user("golden_daily_arena_closed")
    tournament_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.status = "ROUND_1"

    async with SessionLocal.begin() as session:
        with pytest.raises(TournamentClosedError):
            await join_daily_cup_by_id(
                session,
                user_id=user_id,
                tournament_id=tournament_id,
                now_utc=now_utc,
            )


@pytest.mark.asyncio
async def test_daily_arena_messaging_accepts_arena_tournament_id_without_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_ids = await create_users("golden_daily_arena_msg", 2)
    tournament_id = await create_completed_daily_arena(now_utc=now_utc, user_ids=user_ids)
    bot = DummyBot()
    followups: list[str] = []

    async def _fake_deliver(**kwargs) -> dict[str, object]:
        del kwargs
        return {
            "sent": 0,
            "edited": 0,
            "failed": 0,
            "new_message_ids": {},
            "replaced_message_ids": {},
        }

    monkeypatch.setattr(daily_cup_messaging, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_messaging, "deliver_daily_cup_messages", _fake_deliver)
    monkeypatch.setattr(
        daily_cup_messaging,
        "handle_daily_cup_completion_followups",
        lambda **kwargs: followups.append(str(kwargs["tournament_id"])),
    )

    result = await daily_cup_messaging.run_daily_cup_round_messaging_async(
        tournament_id=tournament_id
    )

    assert result["processed"] == 1
    assert result["participants_total"] == 2
    assert bot.session.closed is True
    assert followups == [tournament_id]


@pytest.mark.asyncio
async def test_daily_arena_proof_card_generation_does_not_fail_for_arena_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_id = await create_user("golden_daily_arena_proof")
    tournament_id = await create_completed_daily_arena(now_utc=now_utc, user_ids=[user_id])
    bot = DummyBot()

    async def _fake_send_proof_card(**kwargs) -> tuple[bool, bool, str | None]:
        del kwargs
        return True, False, "proof-file-id"

    async def _fake_get_max_round_no(*args, **kwargs) -> int:
        del args, kwargs
        return 3

    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_proof_cards, "send_daily_cup_proof_card", _fake_send_proof_card)
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentMatchesRepo,
        "get_max_round_no",
        _fake_get_max_round_no,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "is_today_daily_cup_tournament",
        lambda **kwargs: True,
    )

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )

    assert result["processed"] == 1
    assert result["participants_total"] == 1
    assert result["sent"] == 1
    assert bot.session.closed is True
