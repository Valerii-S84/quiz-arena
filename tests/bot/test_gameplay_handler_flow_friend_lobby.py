from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay, gameplay_friend_challenge
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_friend_challenge_type_tournament_shows_soon_text(monkeypatch) -> None:
    callback = DummyCallback(
        data="friend:challenge:type:tournament",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_challenge_type_selected(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.friend.challenge.tournament.soon"]


@pytest.mark.asyncio
async def test_handle_friend_my_duels_groups_sections_with_my_turn_first(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    now = datetime(2026, 2, 27, 18, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 2, 27, 17, 30, tzinfo=timezone.utc)

    async def _fake_list_duels(*args, **kwargs):
        return [
            FriendChallengeSnapshot(
                challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_token="token-a",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="CREATOR_DONE",
                creator_user_id=17,
                opponent_user_id=18,
                current_round=5,
                total_rounds=5,
                creator_score=3,
                opponent_score=1,
                creator_finished_at=finished_at,
                winner_user_id=None,
                expires_at=now,
            ),
            FriendChallengeSnapshot(
                challenge_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                invite_token="token-b",
                challenge_type="OPEN",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="PENDING",
                creator_user_id=17,
                opponent_user_id=None,
                current_round=1,
                total_rounds=12,
                creator_score=0,
                opponent_score=0,
                winner_user_id=None,
                expires_at=now,
            ),
            FriendChallengeSnapshot(
                challenge_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
                invite_token="token-c",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="ACCEPTED",
                creator_user_id=17,
                opponent_user_id=19,
                current_round=2,
                total_rounds=5,
                creator_score=1,
                opponent_score=1,
                winner_user_id=None,
                expires_at=now,
            ),
            FriendChallengeSnapshot(
                challenge_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
                invite_token="token-d",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="COMPLETED",
                creator_user_id=17,
                opponent_user_id=20,
                current_round=5,
                total_rounds=5,
                creator_score=4,
                opponent_score=2,
                winner_user_id=17,
                expires_at=now,
            ),
        ]

    async def _fake_opponent_label(*, challenge, user_id):
        del user_id
        labels = {
            UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"): "Anna",
            UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"): "Freund",
            UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"): "Max",
            UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"): "Klaus",
        }
        return labels[challenge.challenge_id]

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "list_friend_challenges_for_user", _fake_list_duels)
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_opponent_label)

    callback = DummyCallback(
        data="friend:my:duels",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_my_duels(callback)

    text = callback.message.answers[0].text or ""
    my_turn_pos = text.find(TEXTS_DE["msg.friend.challenge.my.my_turn"])
    waiting_pos = text.find(TEXTS_DE["msg.friend.challenge.my.waiting"])
    open_pos = text.find(TEXTS_DE["msg.friend.challenge.my.open"])
    completed_pos = text.find(TEXTS_DE["msg.friend.challenge.my.completed"])
    assert -1 not in {my_turn_pos, waiting_pos, open_pos, completed_pos}
    assert my_turn_pos < waiting_pos < open_pos < completed_pos
