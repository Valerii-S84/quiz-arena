from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.lifecycle import settle_round_and_advance
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


async def _start_daily_cup(
    *,
    monkeypatch,
    now_utc: datetime,
    participants_total: int,
    test_name: str,
) -> UUID:
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"{test_name}_{idx}") for idx in range(participants_total)]
    tournament_id = await _create_daily_cup_registration_tournament(
        now_utc=now_utc,
        max_participants=participants_total,
    )
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)

    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1
    assert int(started["participants_total"]) == participants_total
    return tournament_id


async def _mark_round_completed(
    *,
    tournament_id: UUID,
    round_no: int,
    settled_at: datetime,
) -> None:
    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert matches
        for match in matches:
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id_for_update(
                session,
                match.friend_challenge_id,
            )
            assert challenge is not None
            challenge.status = "COMPLETED"
            challenge.winner_user_id = int(match.user_a)
            if challenge.opponent_user_id is None:
                challenge.creator_score = 5
                challenge.opponent_score = 0
            elif int(challenge.creator_user_id) == int(match.user_a):
                challenge.creator_score = 5
                challenge.opponent_score = 3
            else:
                challenge.creator_score = 3
                challenge.opponent_score = 5
            challenge.creator_finished_at = settled_at
            challenge.opponent_finished_at = settled_at
            challenge.completed_at = settled_at
            challenge.updated_at = settled_at


async def _settle_round_directly(
    *,
    tournament_id: UUID,
    round_no: int,
    settled_at: datetime,
) -> dict[str, int]:
    await _mark_round_completed(
        tournament_id=tournament_id,
        round_no=round_no,
        settled_at=settled_at,
    )
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        return await settle_round_and_advance(
            session,
            tournament=tournament,
            now_utc=settled_at,
        )


async def _expire_round_deadline(
    *,
    tournament_id: UUID,
    round_no: int,
    expired_at: datetime,
) -> None:
    deadline = expired_at - timedelta(minutes=1)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.round_deadline = deadline
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert matches
        for match in matches:
            match.deadline = deadline


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("participants_total", "expected_rounds"),
    [
        (4, 3),
        (20, 3),
        (21, 4),
    ],
)
async def test_settle_round_and_advance_stops_on_expected_final_round(
    monkeypatch,
    participants_total: int,
    expected_rounds: int,
) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    tournament_id = await _start_daily_cup(
        monkeypatch=monkeypatch,
        now_utc=now_utc,
        participants_total=participants_total,
        test_name=f"daily_cup_limit_direct_{participants_total}",
    )

    for round_no in range(1, expected_rounds):
        transition = await _settle_round_directly(
            tournament_id=tournament_id,
            round_no=round_no,
            settled_at=now_utc + timedelta(minutes=round_no),
        )
        assert int(transition["tournament_completed"]) == 0
        assert int(transition["round_started"]) == 1
        assert int(transition["matches_created"]) > 0

    final_transition = await _settle_round_directly(
        tournament_id=tournament_id,
        round_no=expected_rounds,
        settled_at=now_utc + timedelta(minutes=expected_rounds),
    )
    assert int(final_transition["tournament_completed"]) == 1
    assert int(final_transition["round_started"]) == 0
    assert int(final_transition["matches_created"]) == 0

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "COMPLETED"
        assert int(tournament.current_round) == expected_rounds
        unexpected_round = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=expected_rounds + 1,
        )
        assert unexpected_round == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("participants_total", "expected_followups"),
    [
        (4, [False, False, True]),
        (20, [False, False, True]),
        (21, [False, False, False, True]),
    ],
)
async def test_daily_cup_completion_followups_fire_after_expected_final_round(
    monkeypatch,
    participants_total: int,
    expected_followups: list[bool],
) -> None:
    now_utc = datetime(2026, 3, 2, 11, 0, tzinfo=UTC)
    tournament_id = await _start_daily_cup(
        monkeypatch=monkeypatch,
        now_utc=now_utc,
        participants_total=participants_total,
        test_name=f"daily_cup_limit_worker_{participants_total}",
    )

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

    for round_no, expected_completion in enumerate(expected_followups, start=1):
        run_at = now_utc + timedelta(hours=round_no)
        await _expire_round_deadline(
            tournament_id=tournament_id,
            round_no=round_no,
            expired_at=run_at,
        )
        now_state["value"] = run_at
        result = await daily_cup_rounds.advance_daily_cup_rounds_async()
        if expected_completion:
            assert int(result["tournaments_completed_total"]) == 1
            assert int(result["rounds_started_total"]) == 0
        else:
            assert int(result["tournaments_completed_total"]) == 0
            assert int(result["rounds_started_total"]) == 1

    assert round_enqueued == [
        (str(tournament_id), enqueue_completion_followups)
        for enqueue_completion_followups in expected_followups
    ]
