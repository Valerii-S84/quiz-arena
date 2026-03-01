from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.db.models.tournaments import Tournament
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.service import join_daily_cup_by_id
from app.game.tournaments.settlement import settle_pending_match_from_duel
from app.game.tournaments.lifecycle import check_and_advance_round
from app.workers.tasks import daily_cup_async, daily_cup_rounds
from app.workers.tasks.daily_cup_time import get_daily_cup_window
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return None


class _BlockedBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()

    async def send_message(self, **kwargs):
        raise TelegramForbiddenError(
            method=SendMessage(chat_id=int(kwargs["chat_id"]), text="x"),
            message="forbidden",
        )


async def _set_last_seen(*, user_id: int, seen_at: datetime) -> None:
    async with SessionLocal.begin() as session:
        await UsersRepo.touch_last_seen(session, user_id=user_id, seen_at=seen_at)


async def _create_daily_cup_registration_tournament(*, now_utc: datetime) -> UUID:
    window = get_daily_cup_window(now_utc=now_utc)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="REGISTRATION",
                format="QUICK_5",
                max_participants=8,
                current_round=0,
                registration_deadline=window.close_at_utc,
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc,
            ),
        )
        return tournament.id


async def _join_users(*, tournament_id: UUID, user_ids: list[int], now_utc: datetime) -> None:
    async with SessionLocal.begin() as session:
        for user_id in user_ids:
            await join_daily_cup_by_id(
                session,
                user_id=user_id,
                tournament_id=tournament_id,
                now_utc=now_utc,
            )


@pytest.mark.asyncio
async def test_daily_cup_canceled_if_less_than_4(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_ids = [
        await _create_user("daily_cup_cancel_1"),
        await _create_user("daily_cup_cancel_2"),
        await _create_user("daily_cup_cancel_3"),
    ]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "build_bot", lambda: bot)

    result = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(result["canceled"]) == 1
    assert int(result["started"]) == 0
    assert int(result["participants_total"]) == 3

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "CANCELED"

    assert len(bot.messages) == 3


@pytest.mark.asyncio
async def test_daily_cup_starts_with_4_plus(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_start_{idx}") for idx in range(4)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    enqueued: list[str] = []
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(
        daily_cup_async,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id: enqueued.append(tournament_id),
    )

    result = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(result["started"]) == 1
    assert int(result["canceled"]) == 0
    assert enqueued == [str(tournament_id)]

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "ROUND_1"
        assert tournament.current_round == 1
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(matches) == 2


@pytest.mark.asyncio
async def test_daily_cup_round_advance_on_deadline(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    deadline_now = now_utc + timedelta(hours=3)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_deadline_{idx}") for idx in range(4)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    await daily_cup_async.close_daily_cup_registration_and_start_async()

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.round_deadline = deadline_now - timedelta(minutes=1)
        round_one = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(round_one) == 2
        for match in round_one:
            match.deadline = deadline_now - timedelta(minutes=1)

    enqueued_rounds: list[str] = []
    enqueued_proofs: list[str] = []
    monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda: deadline_now)
    monkeypatch.setattr(
        daily_cup_rounds,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id: enqueued_rounds.append(tournament_id),
    )
    monkeypatch.setattr(
        daily_cup_rounds,
        "enqueue_daily_cup_proof_cards",
        lambda *, tournament_id: enqueued_proofs.append(tournament_id),
    )

    result = await daily_cup_rounds.advance_daily_cup_rounds_async()
    assert int(result["matches_settled_total"]) >= 1
    assert int(result["rounds_started_total"]) >= 1
    assert enqueued_rounds == [str(tournament_id)]
    assert enqueued_proofs == []

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "ROUND_2"


@pytest.mark.asyncio
async def test_daily_cup_early_advance(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_early_{idx}") for idx in range(4)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    await daily_cup_async.close_daily_cup_registration_and_start_async()

    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(matches) == 2
        for idx, match in enumerate(matches, start=1):
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id_for_update(
                session, match.friend_challenge_id
            )
            assert challenge is not None
            challenge.status = "COMPLETED"
            challenge.winner_user_id = int(match.user_a)
            challenge.creator_score = 5
            challenge.opponent_score = 3
            challenge.creator_finished_at = now_utc
            challenge.opponent_finished_at = now_utc
            challenge.completed_at = now_utc
            challenge.updated_at = now_utc
            settled = await settle_pending_match_from_duel(session, match=match, now_utc=now_utc)
            assert settled is True

        transition = await check_and_advance_round(
            session,
            tournament_id=tournament_id,
            now_utc=now_utc,
        )
        assert int(transition["round_started"]) == 1

        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "ROUND_2"
        assert tournament.round_deadline is not None
        assert tournament.round_deadline - now_utc <= timedelta(minutes=130)


@pytest.mark.asyncio
async def test_push_only_to_active_users(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    active_1 = await _create_user("daily_cup_active_1")
    active_2 = await _create_user("daily_cup_active_2")
    inactive = await _create_user("daily_cup_inactive")
    never_seen = await _create_user("daily_cup_never_seen")
    await _set_last_seen(user_id=active_1, seen_at=now_utc - timedelta(days=1))
    await _set_last_seen(user_id=active_2, seen_at=now_utc - timedelta(days=6))
    await _set_last_seen(user_id=inactive, seen_at=now_utc - timedelta(days=8))

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "build_bot", lambda: bot)

    result = await daily_cup_async.open_daily_cup_registration_async()
    assert int(result["users_scanned_total"]) == 2
    assert int(result["sent_total"]) == 2
    assert int(result["skipped_total"]) == 0

    sent_ids = {int(message["chat_id"]) for message in bot.messages}
    async with SessionLocal.begin() as session:
        users = await UsersRepo.list_by_ids(session, [active_1, active_2, inactive, never_seen])
    telegram_ids = {int(user.id): int(user.telegram_user_id) for user in users}
    assert sent_ids == {telegram_ids[active_1], telegram_ids[active_2]}


@pytest.mark.asyncio
async def test_push_skips_blocked_users(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    active_user = await _create_user("daily_cup_blocked_user")
    await _set_last_seen(user_id=active_user, seen_at=now_utc - timedelta(days=1))

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "build_bot", lambda: _BlockedBot())

    result = await daily_cup_async.open_daily_cup_registration_async()
    assert int(result["users_scanned_total"]) == 1
    assert int(result["sent_total"]) == 0
    assert int(result["skipped_total"]) == 1
