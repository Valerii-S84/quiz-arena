from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.lifecycle import check_and_advance_round
from app.game.tournaments.settlement import settle_pending_match_from_duel
from app.workers.tasks import daily_cup_async, daily_cup_messaging
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


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.messages))

    async def edit_message_text(self, **kwargs):
        self.messages.append(kwargs)
        return None


async def _advance_to_round(
    *,
    tournament_id,
    target_round: int,
    now_utc: datetime,
) -> None:
    for round_no in range(1, target_round):
        settle_at = now_utc + timedelta(minutes=round_no)
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
                challenge.creator_score = 5
                challenge.opponent_score = 3
                challenge.creator_finished_at = settle_at
                challenge.opponent_finished_at = settle_at
                challenge.completed_at = settle_at
                challenge.updated_at = settle_at
                settled = await settle_pending_match_from_duel(
                    session,
                    match=match,
                    now_utc=settle_at,
                )
                assert settled is True
            transition = await check_and_advance_round(
                session,
                tournament_id=tournament_id,
                now_utc=settle_at,
            )
            assert int(transition["round_started"]) == 1


def _start_button_callbacks(message: dict[str, object]) -> list[str]:
    reply_markup = message["reply_markup"]
    buttons = [button for row in reply_markup.inline_keyboard for button in row]
    return [
        str(button.callback_data)
        for button in buttons
        if button.text == "Runde starten" and button.callback_data is not None
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("target_round", [2, 3, 4])
async def test_daily_cup_round_messaging_rounds_2_to_4_send_round_start_buttons(
    monkeypatch,
    target_round: int,
) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_round_msg_{target_round}_{idx}") for idx in range(4)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)
    monkeypatch.setattr(
        daily_cup_messaging, "enqueue_daily_cup_round_messaging", lambda **kwargs: None
    )
    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1

    await _advance_to_round(tournament_id=tournament_id, target_round=target_round, now_utc=now_utc)

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_messaging, "build_bot", lambda: bot)

    result = await daily_cup_messaging.run_daily_cup_round_messaging_async(
        tournament_id=str(tournament_id)
    )
    assert int(result["sent"]) == 4

    texts = [str(message["text"]) for message in bot.messages]
    assert all(f"⚔️ Runde {target_round}/4 gestartet" in text for text in texts)

    actual_callbacks = Counter(
        callback for message in bot.messages for callback in _start_button_callbacks(message)
    )
    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=target_round,
        )
    expected_callbacks = Counter(
        f"friend:next:{match.friend_challenge_id}"
        for match in matches
        for _ in range(2 if match.user_b is not None else 1)
    )
    assert actual_callbacks == expected_callbacks


@pytest.mark.asyncio
async def test_daily_cup_round_messaging_hides_round_start_button_for_completed_match(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_round_msg_done_{idx}") for idx in range(4)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)
    monkeypatch.setattr(
        daily_cup_messaging, "enqueue_daily_cup_round_messaging", lambda **kwargs: None
    )
    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1

    await _advance_to_round(tournament_id=tournament_id, target_round=2, now_utc=now_utc)

    async with SessionLocal.begin() as session:
        round_two = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=2,
        )
        completed_match = round_two[0]
        completed_match.status = "COMPLETED"
        completed_match.winner_id = int(completed_match.user_a)
        users = await UsersRepo.list_by_ids(
            session,
            [int(completed_match.user_a), int(completed_match.user_b)],
        )
        completed_chat_ids = {int(user.telegram_user_id) for user in users}

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_messaging, "build_bot", lambda: bot)

    result = await daily_cup_messaging.run_daily_cup_round_messaging_async(
        tournament_id=str(tournament_id)
    )
    assert int(result["sent"]) == 4

    messages_by_chat = {int(message["chat_id"]): message for message in bot.messages}
    assert len(messages_by_chat) == 4
    for chat_id in completed_chat_ids:
        assert _start_button_callbacks(messages_by_chat[chat_id]) == []
