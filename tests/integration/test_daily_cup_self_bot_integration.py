from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.sessions.service import GameSessionService
from app.game.sessions.service.friend_challenges_tournament_progress import (
    handle_tournament_duel_progress,
)
from app.game.tournaments.queries import get_daily_cup_lobby_by_id
from app.workers.tasks import daily_cup_async
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_daily_cup_worker_integration import (
    _create_daily_cup_registration_tournament,
    _join_users,
)
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc


async def _create_started_daily_cup_with_self_bot(*, monkeypatch, now_utc: datetime):
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    seed = int(now_utc.timestamp())
    user_ids = [await _create_user(f"daily_cup_self_bot_{seed}_{idx}") for idx in range(5)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(
        daily_cup_async,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id: None,
    )
    result = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(result["started"]) == 1
    return tournament_id


async def _complete_self_bot_match(
    *,
    tournament_id,
    now_utc: datetime,
    creator_score: int,
) -> tuple[object, object, object]:
    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        self_bot_match = next(match for match in matches if match.user_b is None)
        assert self_bot_match.friend_challenge_id is not None

        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session, self_bot_match.friend_challenge_id
        )
        assert challenge is not None
        challenge.creator_score = creator_score
        challenge.creator_answered_round = challenge.total_rounds
        challenge.creator_finished_at = now_utc + timedelta(minutes=5)
        challenge.status = "CREATOR_DONE"
        challenge.updated_at = now_utc + timedelta(minutes=5)

        await handle_tournament_duel_progress(
            session,
            challenge=challenge,
            user_id=int(self_bot_match.user_a),
            now_utc=now_utc + timedelta(minutes=5),
        )

        refreshed_match = await TournamentMatchesRepo.get_by_id_for_update(
            session,
            self_bot_match.id,
        )
        assert refreshed_match is not None

        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )
        self_bot_participant = next(
            item for item in participants if item.user_id == refreshed_match.user_a
        )
        return challenge, refreshed_match, self_bot_participant


@pytest.mark.asyncio
async def test_daily_cup_with_odd_participants_creates_playable_self_bot_match(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 6, 11, 0, tzinfo=UTC)
    tournament_id = await _create_started_daily_cup_with_self_bot(
        monkeypatch=monkeypatch,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "ROUND_1"

        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(matches) == 3

        self_bot_match = next(match for match in matches if match.user_b is None)
        assert self_bot_match.status == "PENDING"
        assert self_bot_match.friend_challenge_id is not None

        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session, self_bot_match.friend_challenge_id
        )
        assert challenge is not None
        assert int(challenge.creator_user_id) == int(self_bot_match.user_a)
        assert int(challenge.opponent_user_id or 0) == int(self_bot_match.user_a)
        assert challenge.status == "ACCEPTED"

        lobby = await get_daily_cup_lobby_by_id(
            session,
            tournament_id=tournament_id,
            viewer_user_id=int(self_bot_match.user_a),
        )
        assert lobby.viewer_current_match_challenge_id == self_bot_match.friend_challenge_id
        assert lobby.viewer_current_opponent_user_id is None


@pytest.mark.asyncio
async def test_daily_cup_round_question_uses_daily_arena_cup_header(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 6, 11, 0, tzinfo=UTC)
    tournament_id = await _create_started_daily_cup_with_self_bot(
        monkeypatch=monkeypatch,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        self_bot_match = next(match for match in matches if match.user_b is None)
        round_start = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=int(self_bot_match.user_a),
            challenge_id=self_bot_match.friend_challenge_id,
            idempotency_key=f"start:daily-cup:test:{self_bot_match.id}",
            now_utc=now_utc,
        )

    assert round_start.start_result is not None
    assert round_start.start_result.session.header_mode_label_override == "Daily Arena Cup"


@pytest.mark.asyncio
async def test_daily_cup_self_bot_three_correct_answers_is_a_win_for_two_points(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 3, 6, 11, 0, tzinfo=UTC)
    tournament_id = await _create_started_daily_cup_with_self_bot(
        monkeypatch=monkeypatch,
        now_utc=now_utc,
    )

    challenge, refreshed_match, self_bot_participant = await _complete_self_bot_match(
        tournament_id=tournament_id,
        now_utc=now_utc,
        creator_score=3,
    )

    assert challenge.status == "COMPLETED"
    assert challenge.opponent_score == 2
    assert challenge.winner_user_id == refreshed_match.user_a
    assert refreshed_match.status == "COMPLETED"
    assert refreshed_match.winner_id == refreshed_match.user_a
    assert float(self_bot_participant.score) == 2.0
    assert float(self_bot_participant.tie_break) == 3.0


@pytest.mark.asyncio
async def test_daily_cup_self_bot_requires_more_than_two_correct_answers_for_tournament_point(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 3, 6, 11, 0, tzinfo=UTC)
    tournament_id = await _create_started_daily_cup_with_self_bot(
        monkeypatch=monkeypatch,
        now_utc=now_utc,
    )

    challenge, refreshed_match, self_bot_participant = await _complete_self_bot_match(
        tournament_id=tournament_id,
        now_utc=now_utc,
        creator_score=2,
    )

    assert challenge.status == "COMPLETED"
    assert challenge.opponent_score == 2
    assert challenge.winner_user_id is None
    assert refreshed_match.status == "COMPLETED"
    assert refreshed_match.winner_id is None
    assert float(self_bot_participant.score) == 1.0
    assert float(self_bot_participant.tie_break) == 2.0


@pytest.mark.asyncio
async def test_daily_cup_self_bot_one_correct_answer_is_a_loss_for_zero_points(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 3, 6, 11, 0, tzinfo=UTC)
    tournament_id = await _create_started_daily_cup_with_self_bot(
        monkeypatch=monkeypatch,
        now_utc=now_utc,
    )

    challenge, refreshed_match, self_bot_participant = await _complete_self_bot_match(
        tournament_id=tournament_id,
        now_utc=now_utc,
        creator_score=1,
    )

    assert challenge.status == "COMPLETED"
    assert challenge.opponent_score == 2
    assert challenge.winner_user_id is None
    assert refreshed_match.status == "COMPLETED"
    assert refreshed_match.winner_id is None
    assert float(self_bot_participant.score) == 0.0
    assert float(self_bot_participant.tie_break) == 1.0
