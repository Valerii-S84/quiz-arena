from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import start
from tests.bot.helpers import DummyMessage, DummySessionLocal


class _StartMessage(DummyMessage):
    def __init__(
        self,
        *,
        text: str,
        from_user: SimpleNamespace | None,
        message_id: int = 100,
    ) -> None:
        super().__init__()
        self.text = text
        self.from_user = from_user
        self.message_id = message_id


def test_extract_tournament_invite_code() -> None:
    assert start._extract_tournament_invite_code("tournament_abcdefabcdef") == "abcdefabcdef"
    assert start._extract_tournament_invite_code("tournament_bad") is None
    assert start._extract_tournament_invite_code(None) is None


@pytest.mark.asyncio
async def test_handle_start_tournament_payload_shows_lobby_and_join_button(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        del session, telegram_user
        assert start_payload == "tournament_abcdefabcdef"
        return SimpleNamespace(user_id=9, free_energy=20, paid_energy=1, current_streak=1)

    async def _fake_lobby_by_code(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_code="abcdefabcdef",
                name="Freunde",
                format="QUICK_5",
                max_participants=8,
                current_round=0,
                status="REGISTRATION",
            ),
            participants=(
                SimpleNamespace(user_id=11, score=0),
                SimpleNamespace(user_id=12, score=0),
            ),
            viewer_joined=False,
            can_start=False,
            viewer_current_match_challenge_id=None,
        )

    async def _fake_list_by_ids(*args, **kwargs):
        del args, kwargs
        return [
            SimpleNamespace(id=11, username="max", first_name="Max"),
            SimpleNamespace(id=12, username="anna", first_name="Anna"),
        ]

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        start.start_flow.TournamentServiceFacade,
        "get_private_tournament_lobby_by_invite_code",
        _fake_lobby_by_code,
    )
    monkeypatch.setattr(start.start_flow.UsersRepo, "list_by_ids", _fake_list_by_ids)

    message = _StartMessage(
        text="/start tournament_abcdefabcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    response = message.answers[0]
    assert "Teilnehmer: 2/8" in (response.text or "")
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:tournament:join:abcdefabcdef" in callbacks
