from __future__ import annotations

import pytest

from app.services.channel_bonus import ChannelBonusService


@pytest.fixture(autouse=True)
def _patch_channel_bonus_defaults(monkeypatch):
    async def _false_is_claimed(session, *, user_id: int) -> bool:
        del session, user_id
        return False

    async def _false_can_show(session, *, user_id: int) -> bool:
        del session, user_id
        return False

    async def _false_post_game_prompt(
        session,
        *,
        user_id: int,
        idempotent_replay: bool,
    ) -> bool:
        del session, user_id, idempotent_replay
        return False

    monkeypatch.setattr(ChannelBonusService, "is_bonus_claimed", _false_is_claimed)
    monkeypatch.setattr(ChannelBonusService, "can_show_prompt", _false_can_show)
    monkeypatch.setattr(
        ChannelBonusService,
        "should_show_post_game_prompt",
        _false_post_game_prompt,
    )
    monkeypatch.setattr(ChannelBonusService, "resolve_channel_url", lambda: None)
