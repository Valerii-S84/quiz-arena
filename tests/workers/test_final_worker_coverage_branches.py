from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image, ImageDraw

from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE
from app.workers.tasks import daily_cup_core, friend_challenges_async
from app.workers.tasks.friend_challenges_proof_card_render_branding import draw_brand_header
from tests.type_helpers import build_friend_challenge
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_ensure_daily_cup_registration_tournament_creates_missing(monkeypatch) -> None:
    created: list[object] = []
    session = SimpleNamespace(execute=lambda *_args, **_kwargs: _async_value(None))

    monkeypatch.setattr(
        daily_cup_core.TournamentsRepo,
        "get_by_type_and_registration_deadline_for_update",
        lambda *_args, **_kwargs: _async_value(None),
    )
    monkeypatch.setattr(
        daily_cup_core, "generate_invite_code", lambda _session: _async_value("INV")
    )
    monkeypatch.setattr(
        daily_cup_core.TournamentsRepo,
        "create",
        lambda _session, *, tournament: _async_append(created, tournament),
    )

    result = asyncio.run(
        daily_cup_core.ensure_daily_cup_registration_tournament(
            session=session,
            now_utc_value=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )

    assert result.invite_code == "INV"
    assert result.status == "REGISTRATION"
    assert created == [result]


@pytest.mark.asyncio
async def test_friend_challenge_deadlines_emits_expired_and_notice_events(monkeypatch) -> None:
    expired = build_friend_challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=22,
        creator_score=4,
        opponent_score=1,
        total_rounds=5,
        winner_user_id=11,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    analytics: list[dict[str, object]] = []

    async def _none(*_args, **_kwargs):
        return []

    async def _joined(*_args, **_kwargs):
        return [expired]

    async def _notify(**_kwargs):
        return (0, 0, 1, 0, [{"kind": "reminder"}], [{"kind": "expired"}])

    async def _emit(_session, **kwargs):
        analytics.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_async,
        "SessionLocal",
        session_local_with_sessions("s1", "s2"),
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_active_due_for_last_chance_for_update",
        _none,
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_pending_due_for_expire_for_update",
        _none,
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_joined_due_for_walkover_for_update",
        _joined,
    )
    monkeypatch.setattr(friend_challenges_async, "send_deadline_notifications", _notify)
    monkeypatch.setattr(friend_challenges_async, "emit_analytics_event", _emit)

    result = await friend_challenges_async.run_friend_challenge_deadlines_async(batch_size=0)

    assert result["batch_size"] == 1
    assert result["expired_total"] == 1
    assert result["expired_notice_sent_total"] == 1
    assert [event["event_type"] for event in analytics] == [
        "duel_expired",
        "friend_challenge_last_chance_sent",
        "friend_challenge_expired_notice_sent",
    ]


def test_draw_brand_header_uses_logo_and_text_fallback() -> None:
    image = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    logo = Image.new("RGBA", (300, 100), (255, 255, 255, 120))

    draw_brand_header(image=image, draw=draw, logo=logo)
    logo_pixel = image.getpixel((540, 60))

    fallback = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    draw_brand_header(image=fallback, draw=ImageDraw.Draw(fallback), logo=None)

    assert cast(tuple[int, int, int, int], logo_pixel)[3] > 0
    assert fallback.getbbox() is not None


async def _async_append(target: list[object], value: object):
    target.append(value)
    return value


async def _async_value(value):
    return value
