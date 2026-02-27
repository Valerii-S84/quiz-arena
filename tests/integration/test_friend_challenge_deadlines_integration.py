from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.game.sessions.service import GameSessionService
from app.workers.tasks.friend_challenges_async import run_friend_challenge_deadlines_async
from tests.integration.friend_challenge_fixtures import UTC, _create_user


def _notifications_stub(
    monkeypatch: pytest.MonkeyPatch, captured_expired_items: list[dict[str, object]]
) -> None:
    async def _fake_notifications(*, now_utc, reminder_items, expired_items):
        del now_utc, reminder_items
        captured_expired_items.extend(expired_items)
        return (0, 0, 0, 0, [], [])

    monkeypatch.setattr(
        "app.workers.tasks.friend_challenges_async.send_deadline_notifications",
        _fake_notifications,
    )


@pytest.mark.asyncio
async def test_deadline_worker_marks_pending_as_expired_and_collects_push_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 20, 13, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_pending_expire_creator")
    captured_expired_items: list[dict[str, object]] = []
    _notifications_stub(monkeypatch, captured_expired_items)

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=5,
        )
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        row.expires_at = now_utc - timedelta(minutes=1)

    result = await run_friend_challenge_deadlines_async(batch_size=10)
    assert result["expired_total"] >= 1

    async with SessionLocal.begin() as session:
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        assert row.status == "EXPIRED"

    assert any(item.get("previous_status") == "PENDING" for item in captured_expired_items)


@pytest.mark.asyncio
async def test_deadline_worker_sets_walkover_with_technical_win_or_draw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 20, 14, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_walkover_creator")
    opponent_user_id = await _create_user("fc_walkover_opponent")
    creator_user_id_2 = await _create_user("fc_walkover_creator_2")
    opponent_user_id_2 = await _create_user("fc_walkover_opponent_2")
    captured_expired_items: list[dict[str, object]] = []
    _notifications_stub(monkeypatch, captured_expired_items)

    async with SessionLocal.begin() as session:
        creator_win = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=5,
        )
        await GameSessionService.join_friend_challenge_by_id(
            session,
            user_id=opponent_user_id,
            challenge_id=creator_win.challenge_id,
            now_utc=now_utc,
        )
        creator_win_row = await FriendChallengesRepo.get_by_id_for_update(
            session,
            creator_win.challenge_id,
        )
        assert creator_win_row is not None
        creator_win_row.status = "CREATOR_DONE"
        creator_win_row.creator_score = 3
        creator_win_row.opponent_score = 2
        creator_win_row.creator_finished_at = now_utc
        creator_win_row.expires_at = now_utc - timedelta(minutes=1)

        draw_case = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id_2,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=5,
        )
        await GameSessionService.join_friend_challenge_by_id(
            session,
            user_id=opponent_user_id_2,
            challenge_id=draw_case.challenge_id,
            now_utc=now_utc,
        )
        draw_row = await FriendChallengesRepo.get_by_id_for_update(session, draw_case.challenge_id)
        assert draw_row is not None
        draw_row.status = "ACCEPTED"
        draw_row.creator_score = 1
        draw_row.opponent_score = 1
        draw_row.expires_at = now_utc - timedelta(minutes=1)

    result = await run_friend_challenge_deadlines_async(batch_size=10)
    assert result["expired_total"] >= 2

    async with SessionLocal.begin() as session:
        creator_win_row = await FriendChallengesRepo.get_by_id_for_update(
            session,
            creator_win.challenge_id,
        )
        assert creator_win_row is not None
        assert creator_win_row.status == "WALKOVER"
        assert creator_win_row.winner_user_id == creator_user_id
        assert creator_win_row.opponent_score == 0

        draw_row = await FriendChallengesRepo.get_by_id_for_update(session, draw_case.challenge_id)
        assert draw_row is not None
        assert draw_row.status == "WALKOVER"
        assert draw_row.winner_user_id is None
        assert draw_row.creator_score == 0
        assert draw_row.opponent_score == 0

    assert any(item.get("status") == "WALKOVER" for item in captured_expired_items)
