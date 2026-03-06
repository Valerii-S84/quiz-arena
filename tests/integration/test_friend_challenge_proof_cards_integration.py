from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.sessions.service import GameSessionService
from app.workers.tasks import friend_challenges_proof_cards
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_private_tournament_worker_integration import _DummyWorkerBot

UTC = timezone.utc


async def _telegram_chat_id(user_id: int) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.get_by_id(session, user_id)
    assert user is not None
    return int(user.telegram_user_id)


@pytest.mark.asyncio
async def test_friend_challenge_proof_cards_send_to_both_users_and_reuse_cache(
    monkeypatch,
) -> None:
    now_utc = datetime.now(UTC)
    creator_user_id = await _create_user("friend_proof_creator")
    opponent_user_id = await _create_user("friend_proof_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=5,
        )
        await GameSessionService.join_friend_challenge_by_id(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            now_utc=now_utc,
        )
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        row.status = "COMPLETED"
        row.creator_score = 4
        row.opponent_score = 2
        row.winner_user_id = creator_user_id
        row.creator_finished_at = now_utc
        row.opponent_finished_at = now_utc
        row.completed_at = now_utc
        row.updated_at = now_utc

    creator_chat_id = await _telegram_chat_id(creator_user_id)
    opponent_chat_id = await _telegram_chat_id(opponent_user_id)

    bot = _DummyWorkerBot()
    monkeypatch.setattr(friend_challenges_proof_cards, "build_bot", lambda: bot)

    first = await friend_challenges_proof_cards.run_friend_challenge_proof_cards_async(
        challenge_id=str(challenge.challenge_id),
    )
    assert int(first["processed"]) == 1
    assert int(first["sent"]) == 2
    assert int(first["cached_reused"]) == 0
    assert all(not isinstance(item["photo"], str) for item in bot.send_photos[:2])
    assert [int(item["chat_id"]) for item in bot.send_photos[:2]] == [
        creator_chat_id,
        opponent_chat_id,
    ]
    assert [str(item["caption"]) for item in bot.send_photos[:2]] == [
        (
            f"🏆 DUELL ERGEBNIS\nScore: Du 4 : Gegner 2\nID: {challenge.challenge_id}\n"
            "📱 https://t.me/Deine_Deutsch_Quiz_bot"
        ),
        (
            f"🏆 DUELL ERGEBNIS\nScore: Du 2 : Gegner 4\nID: {challenge.challenge_id}\n"
            "📱 https://t.me/Deine_Deutsch_Quiz_bot"
        ),
    ]
    inline_queries = [
        button.switch_inline_query
        for item in bot.send_photos[:2]
        for row in item["reply_markup"].inline_keyboard
        for button in row
        if button.switch_inline_query
    ]
    assert inline_queries == [
        f"proof:duel:{challenge.challenge_id}",
        f"proof:duel:{challenge.challenge_id}",
    ]
    share_urls = [
        button.url
        for item in bot.send_photos[:2]
        for row in item["reply_markup"].inline_keyboard
        for button in row
        if button.url
    ]
    assert share_urls == [
        "https://t.me/Deine_Deutsch_Quiz_bot",
        "https://t.me/Deine_Deutsch_Quiz_bot",
    ]

    async with SessionLocal.begin() as session:
        refreshed = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert refreshed is not None
        assert refreshed.creator_proof_card_file_id is not None
        assert refreshed.opponent_proof_card_file_id is not None

    first_batch = len(bot.send_photos)
    second = await friend_challenges_proof_cards.run_friend_challenge_proof_cards_async(
        challenge_id=str(challenge.challenge_id),
    )
    assert int(second["processed"]) == 1
    assert int(second["sent"]) == 2
    assert int(second["cached_reused"]) == 2
    second_batch = bot.send_photos[first_batch:]
    assert len(second_batch) == 2
    assert all(isinstance(item["photo"], str) for item in second_batch)
