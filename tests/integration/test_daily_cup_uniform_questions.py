from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.db.session import SessionLocal
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)

UTC = timezone.utc


async def _create_tournament_duel(
    *,
    creator_user_id: int,
    opponent_user_id: int,
    now_utc: datetime,
    tournament_id: UUID | None,
    tournament_round_no: int | None,
):
    async with SessionLocal.begin() as session:
        return await GameSessionService.create_tournament_match_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            opponent_user_id=opponent_user_id,
            tournament_id=tournament_id,
            tournament_round_no=tournament_round_no,
            mode_code="QUICK_MIX_A1A2",
            total_rounds=5,
            tournament_match_id=uuid4(),
            now_utc=now_utc,
            preferred_levels_by_round=None,
        )


@pytest.mark.asyncio
async def test_daily_cup_uniform_question_ids_for_same_tournament_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 7, 10, 0, tzinfo=UTC)
    await _seed_friend_challenge_questions(now_utc=now_utc)
    user_ids = [await _create_user(f"daily_uniform_{idx}") for idx in range(1, 7)]

    tournament_id = uuid4()
    tournament_duels = [
        await _create_tournament_duel(
            creator_user_id=user_ids[0],
            opponent_user_id=user_ids[1],
            now_utc=now_utc,
            tournament_id=tournament_id,
            tournament_round_no=1,
        ),
        await _create_tournament_duel(
            creator_user_id=user_ids[2],
            opponent_user_id=user_ids[3],
            now_utc=now_utc,
            tournament_id=tournament_id,
            tournament_round_no=1,
        ),
        await _create_tournament_duel(
            creator_user_id=user_ids[4],
            opponent_user_id=user_ids[5],
            now_utc=now_utc,
            tournament_id=tournament_id,
            tournament_round_no=1,
        ),
    ]
    expected_question_ids = tournament_duels[0].question_ids
    assert expected_question_ids
    assert tournament_duels[1].question_ids == expected_question_ids
    assert tournament_duels[2].question_ids == expected_question_ids
    next_round_duel = await _create_tournament_duel(
        creator_user_id=user_ids[0],
        opponent_user_id=user_ids[3],
        now_utc=now_utc,
        tournament_id=tournament_id,
        tournament_round_no=2,
    )
    assert next_round_duel.question_ids != expected_question_ids

    fallback_challenge_ids = iter(
        (
            UUID("00000000-0000-0000-0000-000000000001"),
            UUID("00000000-0000-0000-0000-000000000002"),
        )
    )
    monkeypatch.setattr(
        "app.game.sessions.service.friend_challenges_tournament.uuid4",
        lambda: next(fallback_challenge_ids),
    )
    fallback_duel_a = await _create_tournament_duel(
        creator_user_id=user_ids[0],
        opponent_user_id=user_ids[2],
        now_utc=now_utc,
        tournament_id=None,
        tournament_round_no=None,
    )
    fallback_duel_b = await _create_tournament_duel(
        creator_user_id=user_ids[1],
        opponent_user_id=user_ids[3],
        now_utc=now_utc,
        tournament_id=None,
        tournament_round_no=None,
    )
    assert fallback_duel_a.question_ids != fallback_duel_b.question_ids
