from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import gameplay, gameplay_friend_challenge, gameplay_friend_challenge_manage
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_friend_open_repost_returns_clean_error() -> None:
    callback = DummyCallback(
        data="friend:open:repost:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_friend_challenge.handle_friend_open_repost(callback)

    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_friend_open_repost_blocks_rollout_when_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gameplay_friend_challenge_manage.duel_rollout,
        "is_canonical_duels_enabled",
        lambda: False,
    )
    callback = DummyCallback(
        data="friend:open:repost:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_friend_challenge.handle_friend_open_repost(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.duels.disabled"]


@pytest.mark.asyncio
async def test_handle_friend_delete_marks_expired_challenge_deleted(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_delete(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService, "cancel_friend_challenge_by_creator", _fake_delete
    )

    callback = DummyCallback(
        data="friend:delete:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_delete(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.friend.challenge.deleted"]
