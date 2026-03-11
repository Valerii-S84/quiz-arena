from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import gameplay, gameplay_friend_challenge
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_friend_copy_link_does_not_send_raw_url_message(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_get_snapshot_for_user(session, *, user_id, challenge_id, now_utc):
        del session, user_id, challenge_id, now_utc
        return SimpleNamespace()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot_for_user,
    )

    callback = DummyCallback(
        data="friend:copy:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_challenge_copy_link(callback)

    assert callback.message.answers == []
    assert callback.answer_calls == [
        {"text": TEXTS_DE["msg.friend.challenge.link.share.inline"], "show_alert": False}
    ]
