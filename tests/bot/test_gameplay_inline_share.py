from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot.handlers import gameplay_inline_share
from tests.bot.helpers import DummySessionLocal


class _DummyInlineQuery:
    def __init__(self, *, telegram_user_id: int, query: str) -> None:
        self.from_user = SimpleNamespace(id=telegram_user_id)
        self.query = query
        self.answer_calls: list[dict[str, object]] = []

    async def answer(self, results, **kwargs) -> None:
        self.answer_calls.append({"results": results, "kwargs": kwargs})


@pytest.mark.asyncio
async def test_handle_proof_card_inline_share_returns_daily_cup_photo(monkeypatch) -> None:
    monkeypatch.setattr(gameplay_inline_share, "SessionLocal", DummySessionLocal())

    async def _fake_get_user(session, telegram_user_id: int):
        del session, telegram_user_id
        return SimpleNamespace(id=101)

    async def _fake_get_tournament(session, tournament_id):
        del session, tournament_id
        return SimpleNamespace(type="DAILY_ARENA", status="COMPLETED")

    async def _fake_get_participant(session, *, tournament_id, user_id):
        del session, tournament_id, user_id
        return SimpleNamespace(proof_card_file_id="daily-file-id", score=Decimal("4"))

    async def _fake_list_for_tournament(session, *, tournament_id):
        del session, tournament_id
        return [SimpleNamespace(user_id=101, score=Decimal("4"))]

    monkeypatch.setattr(
        gameplay_inline_share.UsersRepo,
        "get_by_telegram_user_id",
        _fake_get_user,
    )
    monkeypatch.setattr(gameplay_inline_share.TournamentsRepo, "get_by_id", _fake_get_tournament)
    monkeypatch.setattr(
        gameplay_inline_share.TournamentParticipantsRepo,
        "get_for_tournament_user",
        _fake_get_participant,
    )
    monkeypatch.setattr(
        gameplay_inline_share.TournamentParticipantsRepo,
        "list_for_tournament",
        _fake_list_for_tournament,
    )

    inline_query = _DummyInlineQuery(
        telegram_user_id=555,
        query="proof:daily:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    await gameplay_inline_share.handle_proof_card_inline_share(inline_query)

    answer = inline_query.answer_calls[0]
    assert answer["kwargs"] == {"cache_time": 0, "is_personal": True}
    result = answer["results"][0]
    assert result.photo_file_id == "daily-file-id"
    assert (
        result.caption
        == "🏆 Daily Arena Cup\nPlatz #1\nPunkte: 4\n📱 https://t.me/Deine_Deutsch_Quiz_bot"
    )
    assert result.reply_markup.inline_keyboard[0][0].url == "https://t.me/Deine_Deutsch_Quiz_bot"


@pytest.mark.asyncio
async def test_handle_proof_card_inline_share_returns_duel_photo_for_owner(monkeypatch) -> None:
    monkeypatch.setattr(gameplay_inline_share, "SessionLocal", DummySessionLocal())

    async def _fake_get_user(session, telegram_user_id: int):
        del session, telegram_user_id
        return SimpleNamespace(id=202)

    async def _fake_get_challenge(session, challenge_id):
        del session, challenge_id
        return SimpleNamespace(
            status="COMPLETED",
            creator_user_id=101,
            opponent_user_id=202,
            creator_score=4,
            opponent_score=2,
            creator_proof_card_file_id="creator-file-id",
            opponent_proof_card_file_id="opponent-file-id",
        )

    monkeypatch.setattr(
        gameplay_inline_share.UsersRepo,
        "get_by_telegram_user_id",
        _fake_get_user,
    )
    monkeypatch.setattr(
        gameplay_inline_share.FriendChallengesRepo,
        "get_by_id",
        _fake_get_challenge,
    )

    inline_query = _DummyInlineQuery(
        telegram_user_id=777,
        query="proof:duel:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )
    await gameplay_inline_share.handle_proof_card_inline_share(inline_query)

    answer = inline_query.answer_calls[0]
    result = answer["results"][0]
    assert result.photo_file_id == "opponent-file-id"
    assert (
        result.caption
        == "🏆 DUELL ERGEBNIS\nScore: Du 2 : Gegner 4\nID: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb\n📱 https://t.me/Deine_Deutsch_Quiz_bot"
    )
    assert result.reply_markup.inline_keyboard[0][0].url == "https://t.me/Deine_Deutsch_Quiz_bot"


@pytest.mark.asyncio
async def test_handle_proof_card_inline_share_returns_no_results_for_stranger(monkeypatch) -> None:
    monkeypatch.setattr(gameplay_inline_share, "SessionLocal", DummySessionLocal())

    async def _fake_get_user(session, telegram_user_id: int):
        del session, telegram_user_id
        return SimpleNamespace(id=303)

    async def _fake_get_challenge(session, challenge_id):
        del session, challenge_id
        return SimpleNamespace(
            status="COMPLETED",
            creator_user_id=101,
            opponent_user_id=202,
            creator_score=4,
            opponent_score=2,
            creator_proof_card_file_id="creator-file-id",
            opponent_proof_card_file_id="opponent-file-id",
        )

    monkeypatch.setattr(
        gameplay_inline_share.UsersRepo,
        "get_by_telegram_user_id",
        _fake_get_user,
    )
    monkeypatch.setattr(
        gameplay_inline_share.FriendChallengesRepo,
        "get_by_id",
        _fake_get_challenge,
    )

    inline_query = _DummyInlineQuery(
        telegram_user_id=888,
        query="proof:duel:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )
    await gameplay_inline_share.handle_proof_card_inline_share(inline_query)

    answer = inline_query.answer_calls[0]
    assert answer["results"] == []


@pytest.mark.asyncio
async def test_handle_proof_card_inline_share_returns_invite_photo_for_creator(monkeypatch) -> None:
    monkeypatch.setattr(gameplay_inline_share, "SessionLocal", DummySessionLocal())

    async def _fake_get_user(session, telegram_user_id: int):
        del session, telegram_user_id
        return SimpleNamespace(id=303)

    async def _fake_get_challenge(session, challenge_id):
        del session, challenge_id
        return SimpleNamespace(
            creator_user_id=303,
            opponent_user_id=None,
        )

    monkeypatch.setattr(
        gameplay_inline_share.UsersRepo,
        "get_by_telegram_user_id",
        _fake_get_user,
    )
    monkeypatch.setattr(
        gameplay_inline_share.FriendChallengesRepo,
        "get_by_id",
        _fake_get_challenge,
    )
    monkeypatch.setattr(
        gameplay_inline_share,
        "get_settings",
        lambda: SimpleNamespace(resolved_welcome_image_file_id="invite-photo-file-id"),
    )

    inline_query = _DummyInlineQuery(
        telegram_user_id=999,
        query="invite:duel:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )
    await gameplay_inline_share.handle_proof_card_inline_share(inline_query)

    answer = inline_query.answer_calls[0]
    result = answer["results"][0]
    assert result.photo_file_id == "invite-photo-file-id"
    assert "Ich fordere dich heraus" in (result.caption or "")
    assert (
        "https://t.me/Deine_Deutsch_Quiz_bot?start=duel_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        in (result.caption or "")
    )
