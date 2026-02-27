from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay, gameplay_friend_challenge, start_parsing
from app.bot.texts.de import TEXTS_DE
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.friend_challenges.constants import DUEL_TYPE_OPEN
from app.game.sessions.errors import FriendChallengeFullError
from app.game.sessions.service import GameSessionService
from app.workers.tasks import friend_challenges_notifications
from app.workers.tasks.friend_challenges_async import run_friend_challenge_deadlines_async
from tests.bot.helpers import DummyCallback, DummyMessage
from tests.integration.friend_challenge_fixtures import _create_user

UTC = timezone.utc


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _DummyBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.sent_messages: list[dict[str, object]] = []

    async def send_message(self, *, chat_id: int, text: str, reply_markup) -> None:
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )


async def _telegram_chat_id(user_id: int) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.get_by_id(session, user_id)
    assert user is not None
    return int(user.telegram_user_id)


@pytest.mark.asyncio
async def test_direct_duel_end_to_end_12_rounds_completes_and_enqueues_proof_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    creator_user_id = await _create_user("fc_e2e_creator")
    opponent_user_id = await _create_user("fc_e2e_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=12,
        )
        challenge_id = challenge.challenge_id

        start_payload = start_parsing._extract_start_payload(f"/start duel_{challenge_id}")
        parsed_challenge_id = start_parsing._extract_duel_challenge_id(start_payload)
        assert parsed_challenge_id == str(challenge_id)

        joined = await GameSessionService.join_friend_challenge_by_id(
            session,
            user_id=opponent_user_id,
            challenge_id=UUID(parsed_challenge_id),
            now_utc=now_utc + timedelta(seconds=1),
        )
        assert joined.joined_now is True

        for round_no in range(1, 12):
            creator_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=creator_user_id,
                challenge_id=challenge_id,
                idempotency_key=f"fc:e2e:creator:start:{round_no}",
                now_utc=now_utc,
            )
            opponent_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=opponent_user_id,
                challenge_id=challenge_id,
                idempotency_key=f"fc:e2e:opponent:start:{round_no}",
                now_utc=now_utc,
            )
            assert creator_round.start_result is not None
            assert opponent_round.start_result is not None
            await GameSessionService.submit_answer(
                session,
                user_id=creator_user_id,
                session_id=creator_round.start_result.session.session_id,
                selected_option=0,
                idempotency_key=f"fc:e2e:creator:answer:{round_no}",
                now_utc=now_utc,
            )
            await GameSessionService.submit_answer(
                session,
                user_id=opponent_user_id,
                session_id=opponent_round.start_result.session.session_id,
                selected_option=0,
                idempotency_key=f"fc:e2e:opponent:answer:{round_no}",
                now_utc=now_utc,
            )

        creator_round_12 = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge_id,
            idempotency_key="fc:e2e:creator:start:12",
            now_utc=now_utc,
        )
        opponent_round_12 = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge_id,
            idempotency_key="fc:e2e:opponent:start:12",
            now_utc=now_utc,
        )
        assert creator_round_12.start_result is not None
        assert opponent_round_12.start_result is not None
        opponent_final_session_id = opponent_round_12.start_result.session.session_id

        await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=creator_round_12.start_result.session.session_id,
            selected_option=0,
            idempotency_key="fc:e2e:creator:answer:12",
            now_utc=now_utc,
        )

    queued_challenges: list[str] = []

    def _fake_enqueue(*, challenge_id: str) -> None:
        queued_challenges.append(challenge_id)

    monkeypatch.setattr(gameplay.gameplay_proof_cards, "enqueue_duel_proof_cards", _fake_enqueue)

    opponent_chat_id = await _telegram_chat_id(opponent_user_id)
    callback = DummyCallback(
        data=f"answer:{opponent_final_session_id}:0",
        from_user=SimpleNamespace(
            id=opponent_chat_id,
            username="opponent",
            first_name="Opponent",
            language_code="de",
        ),
        message=DummyMessage(),
    )
    await gameplay.handle_answer(callback)

    async with SessionLocal.begin() as session:
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
        assert row is not None
        assert row.status == "COMPLETED"
        assert row.creator_finished_at is not None
        assert row.opponent_finished_at is not None
        assert isinstance(row.creator_score, int)
        assert isinstance(row.opponent_score, int)

    assert queued_challenges == [str(challenge_id)]


@pytest.mark.asyncio
async def test_open_duel_race_condition_allows_only_one_accept() -> None:
    now_utc = datetime.now(UTC)
    creator_user_id = await _create_user("fc_open_race_creator")
    first_opponent_user_id = await _create_user("fc_open_race_first")
    second_opponent_user_id = await _create_user("fc_open_race_second")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            challenge_type=DUEL_TYPE_OPEN,
            total_rounds=5,
        )

    async def _accept(user_id: int):
        async with SessionLocal.begin() as session:
            return await GameSessionService.join_friend_challenge_by_id(
                session,
                user_id=user_id,
                challenge_id=challenge.challenge_id,
                now_utc=now_utc + timedelta(seconds=1),
            )

    first_result, second_result = await asyncio.gather(
        _accept(first_opponent_user_id),
        _accept(second_opponent_user_id),
        return_exceptions=True,
    )
    outcomes = [first_result, second_result]
    success = [item for item in outcomes if not isinstance(item, Exception)]
    failures = [item for item in outcomes if isinstance(item, Exception)]

    assert len(success) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], FriendChallengeFullError)
    assert success[0].joined_now is True

    async with SessionLocal.begin() as session:
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        assert row.status == "ACCEPTED"
        assert row.opponent_user_id in {first_opponent_user_id, second_opponent_user_id}


@pytest.mark.asyncio
async def test_ttl_pending_expired_worker_sets_status_and_pushes_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    creator_user_id = await _create_user("fc_ttl_pending_creator")
    creator_chat_id = await _telegram_chat_id(creator_user_id)

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

    bot = _DummyBot()
    monkeypatch.setattr(friend_challenges_notifications, "build_bot", lambda: bot)

    result = await run_friend_challenge_deadlines_async(batch_size=10)
    assert int(result["expired_total"]) >= 1

    async with SessionLocal.begin() as session:
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        assert row.status == "EXPIRED"

    assert any(
        item["chat_id"] == creator_chat_id and "Niemand hat angenommen" in str(item["text"])
        for item in bot.sent_messages
    )


@pytest.mark.asyncio
async def test_meine_duelle_prioritizes_my_turn_before_waiting_and_open() -> None:
    now_utc = datetime.now(UTC)
    creator_user_id = await _create_user("fc_my_duels_creator")
    my_turn_opponent_user_id = await _create_user("fc_my_duels_my_turn")
    waiting_opponent_user_id = await _create_user("fc_my_duels_waiting")

    async with SessionLocal.begin() as session:
        my_turn = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=12,
        )
        await GameSessionService.join_friend_challenge_by_id(
            session,
            user_id=my_turn_opponent_user_id,
            challenge_id=my_turn.challenge_id,
            now_utc=now_utc,
        )

        waiting = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=5,
        )
        await GameSessionService.join_friend_challenge_by_id(
            session,
            user_id=waiting_opponent_user_id,
            challenge_id=waiting.challenge_id,
            now_utc=now_utc,
        )
        waiting_row = await FriendChallengesRepo.get_by_id_for_update(session, waiting.challenge_id)
        assert waiting_row is not None
        waiting_row.status = "CREATOR_DONE"
        waiting_row.creator_finished_at = now_utc
        waiting_row.creator_answered_round = waiting_row.total_rounds

        await GameSessionService._create_friend_challenge_row(
            session,
            creator_user_id=creator_user_id,
            opponent_user_id=None,
            challenge_type=DUEL_TYPE_OPEN,
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            total_rounds=5,
            now_utc=now_utc,
        )

    creator_chat_id = await _telegram_chat_id(creator_user_id)
    callback = DummyCallback(
        data="friend:my:duels",
        from_user=SimpleNamespace(
            id=creator_chat_id,
            username="creator",
            first_name="Creator",
            language_code="de",
        ),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_my_duels(callback)

    text = callback.message.answers[0].text or ""
    my_turn_pos = text.find(TEXTS_DE["msg.friend.challenge.my.my_turn"])
    waiting_pos = text.find(TEXTS_DE["msg.friend.challenge.my.waiting"])
    open_pos = text.find(TEXTS_DE["msg.friend.challenge.my.open"])
    assert -1 not in {my_turn_pos, waiting_pos, open_pos}
    assert my_turn_pos < waiting_pos < open_pos
