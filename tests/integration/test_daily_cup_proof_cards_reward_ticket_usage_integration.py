from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.session import SessionLocal
from app.game.sessions.errors import FriendChallengePaymentRequiredError
from app.game.sessions.service import GameSessionService
from app.workers.tasks import daily_cup_proof_cards
from tests.integration.daily_cup_proof_cards_test_support import (
    create_daily_cup_users,
    ensure_tournament_schema,
    fixed_daily_cup_now,
    install_recording_worker_bot,
)
from tests.integration.daily_cup_winner_rewards_test_support import (
    create_completed_daily_cup_with_bye_seeded_scores,
)

UTC = timezone.utc


class _FrozenDateTime(datetime):
    current = datetime(2026, 4, 24, 10, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


@pytest.mark.asyncio
async def test_daily_cup_second_place_reward_tickets_allow_two_paid_friend_challenges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_reward_ticket_usage", count=13)
    tournament_id = await create_completed_daily_cup_with_bye_seeded_scores(
        now_utc=now_utc,
        user_ids=user_ids,
    )

    _FrozenDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", _FrozenDateTime)
    install_recording_worker_bot(monkeypatch)

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )
    assert result["processed"] == 1

    reward_user_id = user_ids[1]
    async with SessionLocal.begin() as session:
        first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=reward_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=1),
        )
        second = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=reward_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=2),
        )
        paid_first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=reward_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=3),
        )
        paid_second = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=reward_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=4),
        )

        assert first.access_type == "FREE"
        assert second.access_type == "FREE"
        assert paid_first.access_type == "PAID_TICKET"
        assert paid_second.access_type == "PAID_TICKET"

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=reward_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=5),
            )
