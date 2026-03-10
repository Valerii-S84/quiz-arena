from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_cup_async, daily_cup_messaging, daily_cup_rounds
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_daily_cup_worker_integration import (
    _create_daily_cup_registration_tournament,
    _ensure_tournament_schema,
    _join_users,
)

UTC = timezone.utc


@pytest.mark.asyncio
async def test_daily_cup_e2e_with_6_participants_reaches_completed(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_e2e6_{idx}") for idx in range(6)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    start_enqueued: list[str] = []
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(
        daily_cup_async,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id: start_enqueued.append(tournament_id),
    )

    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1
    assert int(started["participants_total"]) == 6
    assert start_enqueued == [str(tournament_id)]

    async with SessionLocal.begin() as session:
        round_one = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(round_one) == 3
        assert all(match.status == "PENDING" for match in round_one)

    now_state = {"value": now_utc}
    round_enqueued: list[tuple[str, bool]] = []
    monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda: now_state["value"])
    monkeypatch.setattr(
        daily_cup_messaging,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id, enqueue_completion_followups=False: round_enqueued.append(
            (tournament_id, bool(enqueue_completion_followups))
        ),
    )

    async def _expire_and_advance(*, round_no: int, run_at: datetime) -> dict[str, int]:
        expired_deadline = run_at - timedelta(minutes=1)
        async with SessionLocal.begin() as session:
            tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
            assert tournament is not None
            tournament.round_deadline = expired_deadline
            round_matches = await TournamentMatchesRepo.list_by_tournament_round(
                session,
                tournament_id=tournament_id,
                round_no=round_no,
            )
            assert len(round_matches) == 3
            for match in round_matches:
                match.deadline = expired_deadline
        now_state["value"] = run_at
        return await daily_cup_rounds.advance_daily_cup_rounds_async()

    first_advance = await _expire_and_advance(round_no=1, run_at=now_utc + timedelta(hours=2))
    second_advance = await _expire_and_advance(round_no=2, run_at=now_utc + timedelta(hours=3))
    third_advance = await _expire_and_advance(round_no=3, run_at=now_utc + timedelta(hours=4))

    assert int(first_advance["rounds_started_total"]) >= 1
    assert int(second_advance["rounds_started_total"]) >= 1
    assert int(third_advance["tournaments_completed_total"]) >= 1
    assert round_enqueued == [
        (str(tournament_id), False),
        (str(tournament_id), False),
        (str(tournament_id), True),
    ]

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "COMPLETED"
        assert tournament.round_deadline is None
        previous_pairs: set[frozenset[int]] = set()
        for round_no in (1, 2, 3):
            matches = await TournamentMatchesRepo.list_by_tournament_round(
                session,
                tournament_id=tournament_id,
                round_no=round_no,
            )
            assert len(matches) == 3
            assert all(match.status in {"COMPLETED", "WALKOVER"} for match in matches)
            for match in matches:
                assert match.user_b is not None
                pair_key = frozenset((int(match.user_a), int(match.user_b)))
                assert pair_key not in previous_pairs
                previous_pairs.add(pair_key)
