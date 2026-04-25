from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.game.sessions.service.friend_challenges_tournament_daily_cup import (
    _tighten_daily_cup_match_deadline,
)

UTC = timezone.utc


def _build_challenge(*, status: str) -> FriendChallenge:
    now_utc = datetime(2026, 3, 7, 11, 0, tzinfo=UTC)
    return FriendChallenge(
        id=uuid4(),
        invite_token=uuid4().hex[:16],
        creator_user_id=11,
        opponent_user_id=22,
        challenge_type="DIRECT",
        mode_code="QUICK_5",
        access_type="FREE",
        question_ids=None,
        tournament_match_id=uuid4(),
        status=status,
        current_round=7,
        total_rounds=7,
        series_id=None,
        series_game_number=1,
        series_best_of=1,
        creator_score=4,
        opponent_score=0,
        creator_answered_round=7,
        opponent_answered_round=0,
        winner_user_id=None,
        creator_finished_at=now_utc,
        opponent_finished_at=None,
        creator_push_count=0,
        opponent_push_count=0,
        creator_proof_card_file_id=None,
        opponent_proof_card_file_id=None,
        expires_at=now_utc + timedelta(hours=1),
        expires_last_chance_notified_at=None,
        created_at=now_utc - timedelta(minutes=10),
        updated_at=now_utc,
        completed_at=None,
    )


def _build_match(*, deadline: datetime, status: str = "PENDING") -> TournamentMatch:
    return TournamentMatch(
        id=uuid4(),
        tournament_id=uuid4(),
        round_no=1,
        round_number=None,
        user_a=11,
        user_b=22,
        bracket_slot_a=None,
        bracket_slot_b=None,
        friend_challenge_id=uuid4(),
        match_timeout_task_id=None,
        player_a_finished_at=None,
        player_b_finished_at=None,
        status=status,
        winner_id=None,
        deadline=deadline,
    )


def test_tighten_daily_cup_match_deadline_shortens_pending_match_after_first_finish() -> None:
    now_utc = datetime(2026, 3, 7, 11, 5, tzinfo=UTC)
    match = _build_match(deadline=now_utc + timedelta(hours=1))

    _tighten_daily_cup_match_deadline(
        challenge=_build_challenge(status="CREATOR_DONE"),
        tournament_match=match,
        now_utc=now_utc,
        grace_minutes=15,
    )

    assert match.deadline == now_utc + timedelta(minutes=15)


def test_tighten_daily_cup_match_deadline_ignores_completed_duels_and_non_pending_matches() -> None:
    now_utc = datetime(2026, 3, 7, 11, 5, tzinfo=UTC)
    completed_duel_match = _build_match(deadline=now_utc + timedelta(hours=1))
    completed_match = _build_match(
        deadline=now_utc + timedelta(hours=1),
        status="COMPLETED",
    )

    _tighten_daily_cup_match_deadline(
        challenge=_build_challenge(status="COMPLETED"),
        tournament_match=completed_duel_match,
        now_utc=now_utc,
        grace_minutes=15,
    )
    _tighten_daily_cup_match_deadline(
        challenge=_build_challenge(status="CREATOR_DONE"),
        tournament_match=completed_match,
        now_utc=now_utc,
        grace_minutes=15,
    )

    assert completed_duel_match.deadline == now_utc + timedelta(hours=1)
    assert completed_match.deadline == now_utc + timedelta(hours=1)
