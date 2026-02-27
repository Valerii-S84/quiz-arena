from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay, gameplay_tournaments
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_tournament_create_from_format_sends_share_lobby(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_create_tournament(*args, **kwargs):
        return SimpleNamespace(
            format="QUICK_5",
            invite_code="abcdefabcdef",
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        )

    async def _fake_invite_link(callback, *, invite_code: str):
        del callback
        assert invite_code == "abcdefabcdef"
        return "https://t.me/testbot?start=tournament_abcdefabcdef"

    emitted: list[str] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(str(kwargs.get("event_type")))

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay,
        "_tournament_service",
        SimpleNamespace(create_private_tournament=_fake_create_tournament),
    )
    monkeypatch.setattr(gameplay, "_build_tournament_invite_link", _fake_invite_link)
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="friend:tournament:format:5",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_tournaments.handle_tournament_create_from_format(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.tournament.created"]
    urls = [button.url for row in response.kwargs["reply_markup"].inline_keyboard for button in row]
    assert any(url and "https://t.me/share/url" in url for url in urls)
    assert emitted == ["private_tournament_created"]


@pytest.mark.asyncio
async def test_handle_tournament_share_result_sends_share_keyboard_and_emits_event(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_lobby(*args, **kwargs):
        return SimpleNamespace(
            tournament=SimpleNamespace(status="COMPLETED"),
            participants=(
                SimpleNamespace(user_id=17, score=Decimal("2")),
                SimpleNamespace(user_id=18, score=Decimal("1")),
            ),
            viewer_joined=True,
        )

    async def _fake_share_url(callback, *, share_text: str):
        del callback
        assert "#1" in share_text
        return "https://t.me/share/url?url=x&text=y"

    emitted: list[str] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(str(kwargs.get("event_type")))

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay,
        "_tournament_service",
        SimpleNamespace(get_private_tournament_lobby_by_id=_fake_lobby),
    )
    monkeypatch.setattr(gameplay, "_build_tournament_share_result_url", _fake_share_url)
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="friend:tournament:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_tournaments.handle_tournament_share(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.tournament.share.ready"]
    urls = [button.url for row in response.kwargs["reply_markup"].inline_keyboard for button in row]
    assert any(url and "https://t.me/share/url" in url for url in urls)
    assert emitted == ["private_tournament_result_shared"]
