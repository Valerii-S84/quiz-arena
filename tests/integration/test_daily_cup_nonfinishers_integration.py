from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.bot.texts.de import TEXTS_DE
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_cup_nonfinishers_summary
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_private_tournament_worker_integration import _ensure_tournament_schema

UTC = timezone.utc


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs) -> None:
        self.messages.append(kwargs)


async def _create_completed_daily_cup_with_nonfinisher(
    *,
    now_utc: datetime,
    user_ids: list[int],
    rounds_played: int,
    incomplete_round: int,
) -> str:
    nonfinisher_user_id = user_ids[0]
    opponent_user_id = user_ids[1]

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="COMPLETED",
                format="QUICK_5",
                max_participants=100,
                current_round=rounds_played,
                registration_deadline=now_utc - timedelta(hours=5),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc - timedelta(hours=6),
            ),
        )
        for index, user_id in enumerate(user_ids):
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
                joined_at=now_utc - timedelta(hours=4) + timedelta(minutes=index),
            )

        for round_number in range(1, rounds_played + 1):
            challenge_id = uuid4()
            is_incomplete_round = round_number == incomplete_round
            await FriendChallengesRepo.create(
                session,
                challenge=FriendChallenge(
                    id=challenge_id,
                    invite_token=uuid4().hex,
                    creator_user_id=nonfinisher_user_id,
                    opponent_user_id=opponent_user_id,
                    challenge_type="DIRECT",
                    mode_code="QUICK_MIX_A1A2",
                    access_type="FREE",
                    question_ids=[],
                    tournament_match_id=None,
                    status="ACCEPTED",
                    current_round=1,
                    total_rounds=7,
                    series_id=None,
                    series_game_number=1,
                    series_best_of=1,
                    creator_score=0,
                    opponent_score=0,
                    creator_answered_round=3 if is_incomplete_round else 7,
                    opponent_answered_round=7,
                    winner_user_id=None,
                    creator_finished_at=None if is_incomplete_round else now_utc,
                    opponent_finished_at=now_utc,
                    creator_push_count=0,
                    opponent_push_count=0,
                    creator_proof_card_file_id=None,
                    opponent_proof_card_file_id=None,
                    expires_at=now_utc + timedelta(hours=1),
                    expires_last_chance_notified_at=None,
                    created_at=now_utc - timedelta(hours=2),
                    updated_at=now_utc - timedelta(hours=1),
                    completed_at=None,
                ),
            )
            session.add(
                TournamentMatch(
                    id=uuid4(),
                    tournament_id=tournament.id,
                    round_no=round_number,
                    round_number=None,
                    user_a=nonfinisher_user_id,
                    user_b=opponent_user_id,
                    bracket_slot_a=None,
                    bracket_slot_b=None,
                    friend_challenge_id=challenge_id,
                    match_timeout_task_id=None,
                    player_a_finished_at=None,
                    player_b_finished_at=None,
                    status="COMPLETED",
                    winner_id=opponent_user_id,
                    deadline=now_utc - timedelta(minutes=round_number),
                )
            )

        return str(tournament.id)


@pytest.mark.asyncio
async def test_daily_cup_nonfinishers_summary_checks_three_round_tournament(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_ids = [await _create_user(f"daily_cup_nonfinish_three_{idx}") for idx in range(4)]
    tournament_id = await _create_completed_daily_cup_with_nonfinisher(
        now_utc=now_utc,
        user_ids=user_ids,
        rounds_played=3,
        incomplete_round=3,
    )

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_nonfinishers_summary, "build_bot", lambda: bot)

    result = await daily_cup_nonfinishers_summary.run_daily_cup_nonfinishers_summary_async(
        tournament_id=tournament_id,
    )

    assert result == {
        "processed": 1,
        "participants_total": 4,
        "nonfinishers_total": 1,
        "sent": 1,
        "failed": 0,
    }
    assert len(bot.messages) == 1
    assert bot.messages[0]["text"] == TEXTS_DE["msg.daily_cup.not_finished_summary"]


@pytest.mark.asyncio
async def test_daily_cup_nonfinishers_summary_checks_four_round_tournament(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 12, 30, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_ids = [await _create_user(f"daily_cup_nonfinish_four_{idx}") for idx in range(21)]
    tournament_id = await _create_completed_daily_cup_with_nonfinisher(
        now_utc=now_utc,
        user_ids=user_ids,
        rounds_played=4,
        incomplete_round=4,
    )

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_nonfinishers_summary, "build_bot", lambda: bot)

    result = await daily_cup_nonfinishers_summary.run_daily_cup_nonfinishers_summary_async(
        tournament_id=tournament_id,
    )

    assert result == {
        "processed": 1,
        "participants_total": 21,
        "nonfinishers_total": 1,
        "sent": 1,
        "failed": 0,
    }
    assert len(bot.messages) == 1
    assert bot.messages[0]["text"] == TEXTS_DE["msg.daily_cup.not_finished_summary"]
