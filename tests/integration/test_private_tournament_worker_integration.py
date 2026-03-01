from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal, engine
from app.game.tournaments.service import (
    create_private_tournament,
    join_private_tournament_by_code,
    start_private_tournament,
)
from app.workers.tasks import tournaments_async, tournaments_messaging
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)

UTC = timezone.utc


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _DummyPhoto:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class _DummyMessage:
    def __init__(self, *, message_id: int, file_id: str | None = None) -> None:
        self.message_id = message_id
        self.photo = [_DummyPhoto(file_id)] if file_id is not None else []


class _DummyWorkerBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.send_messages: list[dict[str, object]] = []
        self.edit_messages: list[dict[str, object]] = []
        self.send_photos: list[dict[str, object]] = []
        self._message_id = 1000
        self._file_id = 0

    async def get_me(self):
        return type("BotMe", (), {"username": "quizarenabot"})()

    async def send_message(self, **kwargs) -> _DummyMessage:
        self.send_messages.append(kwargs)
        self._message_id += 1
        return _DummyMessage(message_id=self._message_id)

    async def edit_message_text(self, **kwargs) -> None:
        self.edit_messages.append(kwargs)

    async def send_photo(self, **kwargs) -> _DummyMessage:
        self.send_photos.append(kwargs)
        photo_payload = kwargs.get("photo")
        if isinstance(photo_payload, str):
            resolved_file_id = photo_payload
        else:
            self._file_id += 1
            resolved_file_id = f"tournament-photo-{self._file_id}"
        return _DummyMessage(message_id=0, file_id=resolved_file_id)


async def _ensure_tournament_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(TournamentMatch.__table__.drop, checkfirst=True)
        await conn.run_sync(TournamentParticipant.__table__.drop, checkfirst=True)
        await conn.run_sync(Tournament.__table__.drop, checkfirst=True)
        await conn.run_sync(Tournament.__table__.create, checkfirst=True)
        await conn.run_sync(TournamentParticipant.__table__.create, checkfirst=True)
        await conn.run_sync(TournamentMatch.__table__.create, checkfirst=True)


@pytest.mark.asyncio
async def test_worker_advances_round_after_deadline_when_match_is_settled(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    creator_user_id = await _create_user("private_tournament_worker_creator")
    opponent_user_id = await _create_user("private_tournament_worker_opponent")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_5",
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=opponent_user_id,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament.tournament_id,
            now_utc=now_utc,
        )
        round_one_matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.tournament_id,
            round_no=1,
        )
        assert len(round_one_matches) == 1
        round_one_match = round_one_matches[0]
        assert round_one_match.friend_challenge_id is not None

        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session, round_one_match.friend_challenge_id
        )
        assert challenge is not None
        challenge.status = "COMPLETED"
        challenge.winner_user_id = opponent_user_id
        challenge.creator_score = 2
        challenge.opponent_score = 3
        challenge.creator_finished_at = now_utc
        challenge.opponent_finished_at = now_utc
        challenge.completed_at = now_utc
        challenge.updated_at = now_utc

        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        tournament_row.round_deadline = now_utc - timedelta(minutes=1)
        round_one_match.deadline = now_utc - timedelta(minutes=1)

    enqueued_rounds: list[str] = []
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_round_messaging",
        lambda *, tournament_id: enqueued_rounds.append(tournament_id),
    )
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_proof_cards",
        lambda *, tournament_id: None,
    )

    result = await tournaments_async.run_private_tournament_rounds_async(batch_size=20)
    assert int(result["rounds_started_total"]) >= 1
    assert int(result["matches_settled_total"]) >= 1
    assert int(result["matches_created_total"]) >= 1
    assert enqueued_rounds == [str(tournament.tournament_id)]

    async with SessionLocal.begin() as session:
        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        assert tournament_row.status == "ROUND_2"
        assert tournament_row.current_round == 2
        assert tournament_row.round_deadline is not None

        round_two_matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.tournament_id,
            round_no=2,
        )
        assert len(round_two_matches) == 1
        assert round_two_matches[0].status == "PENDING"
        assert round_two_matches[0].friend_challenge_id is not None

        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert len(participants) == 2
        top_score = max(float(item.score) for item in participants)
        assert top_score >= 1.0


@pytest.mark.asyncio
async def test_worker_marks_tournament_completed_after_round_three_deadline(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    creator_user_id = await _create_user("private_tournament_worker_final_creator")
    opponent_user_id = await _create_user("private_tournament_worker_final_opponent")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_5",
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=opponent_user_id,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament.tournament_id,
            now_utc=now_utc,
        )
        round_one_matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.tournament_id,
            round_no=1,
        )
        assert len(round_one_matches) == 1
        match = round_one_matches[0]
        assert match.friend_challenge_id is not None

        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session, match.friend_challenge_id
        )
        assert challenge is not None
        challenge.status = "COMPLETED"
        challenge.winner_user_id = creator_user_id
        challenge.creator_score = 4
        challenge.opponent_score = 1
        challenge.creator_finished_at = now_utc
        challenge.opponent_finished_at = now_utc
        challenge.completed_at = now_utc
        challenge.updated_at = now_utc

        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        tournament_row.current_round = 3
        tournament_row.status = "ROUND_3"
        tournament_row.round_deadline = now_utc - timedelta(minutes=1)
        match.round_no = 3
        match.deadline = now_utc - timedelta(minutes=1)

    enqueued_rounds: list[str] = []
    enqueued_proofs: list[str] = []
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_round_messaging",
        lambda *, tournament_id: enqueued_rounds.append(tournament_id),
    )
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_proof_cards",
        lambda *, tournament_id: enqueued_proofs.append(tournament_id),
    )

    result = await tournaments_async.run_private_tournament_rounds_async(batch_size=20)
    assert int(result["tournaments_completed_total"]) >= 1
    assert enqueued_rounds == [str(tournament.tournament_id)]
    assert enqueued_proofs == [str(tournament.tournament_id)]

    async with SessionLocal.begin() as session:
        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        assert tournament_row.status == "COMPLETED"
        assert tournament_row.round_deadline is None


@pytest.mark.asyncio
async def test_round_messaging_sends_once_then_updates_by_edit(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    creator_user_id = await _create_user("private_tournament_round_msg_creator")
    opponent_user_id = await _create_user("private_tournament_round_msg_opponent")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_5",
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=opponent_user_id,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament.tournament_id,
            now_utc=now_utc,
        )
        tournament_id = str(tournament.tournament_id)

    bot = _DummyWorkerBot()
    monkeypatch.setattr(tournaments_messaging, "build_bot", lambda: bot)

    first = await tournaments_messaging.run_private_tournament_round_messaging_async(
        tournament_id=tournament_id
    )
    assert int(first["sent"]) == 2
    assert int(first["edited"]) == 0
    assert len(bot.send_messages) == 2
    assert any("Runde 1/3 gestartet" in str(item.get("text")) for item in bot.send_messages)
    callbacks = [
        button.callback_data
        for row in bot.send_messages[0]["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    urls = [
        button.url
        for row in bot.send_messages[0]["reply_markup"].inline_keyboard
        for button in row
        if button.url
    ]
    assert any(callback.startswith("friend:next:") for callback in callbacks)
    assert any(url and "https://t.me/share/url" in url for url in urls)

    second = await tournaments_messaging.run_private_tournament_round_messaging_async(
        tournament_id=tournament_id
    )
    assert int(second["sent"]) == 0
    assert int(second["edited"]) == 2
    assert len(bot.edit_messages) == 2

    async with SessionLocal.begin() as session:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=UUID(tournament_id),
        )
        assert all(item.standings_message_id is not None for item in participants)
