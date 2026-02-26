from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.bot.handlers import referral
from app.bot.texts.de import TEXTS_DE
from app.economy.referrals.constants import REWARD_CODE_MEGA_PACK
from app.economy.referrals.service import ReferralClaimResult, ReferralOverview
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


class _ReferralMessage(DummyMessage):
    def __init__(self, *, from_user: SimpleNamespace | None) -> None:
        super().__init__()
        self.from_user = from_user


def _overview(*, claimable: int = 0) -> ReferralOverview:
    return ReferralOverview(
        referral_code="ABC123",
        qualified_total=3,
        rewarded_total=1,
        progress_qualified=2,
        progress_target=3,
        pending_rewards_total=1,
        claimable_rewards=claimable,
        deferred_rewards=0,
        next_reward_at_utc=datetime.now(timezone.utc),
    )


def test_build_claim_status_text_variants() -> None:
    claim = ReferralClaimResult(
        status="CLAIMED", reward_code=REWARD_CODE_MEGA_PACK, overview=_overview()
    )
    assert (
        referral._build_claim_status_text(claim) == TEXTS_DE["msg.referral.reward.claimed.megapack"]
    )

    claim = ReferralClaimResult(status="TOO_EARLY", reward_code=None, overview=_overview())
    assert referral._build_claim_status_text(claim) == TEXTS_DE["msg.referral.reward.too_early"]


def test_build_overview_text_uses_fallback_without_link() -> None:
    text = referral._build_overview_text(overview=_overview(), invite_link=None)
    assert "ref_ABC123" in text


@pytest.mark.asyncio
async def test_handle_referral_command_rejects_missing_user() -> None:
    message = _ReferralMessage(from_user=None)

    await referral.handle_referral_command(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.system.error"]


@pytest.mark.asyncio
async def test_handle_referral_command_renders_overview(monkeypatch) -> None:
    async def _fake_load_overview(*, telegram_user, now_utc):
        return _overview(claimable=1)

    async def _fake_invite_link(bot, *, referral_code: str):
        return "https://t.me/testbot?start=ref_ABC123"

    monkeypatch.setattr(referral, "_load_overview", _fake_load_overview)
    monkeypatch.setattr(referral, "_build_invite_link", _fake_invite_link)

    message = _ReferralMessage(from_user=SimpleNamespace(id=1))
    await referral.handle_referral_command(message)

    response = message.answers[0]
    assert TEXTS_DE["msg.referral.invite"] in (response.text or "")
    assert "https://t.me/" not in (response.text or "")
    keyboard = response.kwargs["reply_markup"]
    callbacks = [
        button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data
    ]
    assert "referral:share" in callbacks


@pytest.mark.asyncio
async def test_handle_referral_reward_choice_rejects_invalid_callback() -> None:
    callback = DummyCallback(data="referral:reward:UNKNOWN", from_user=SimpleNamespace(id=1))

    await referral.handle_referral_reward_choice(callback)

    assert callback.answer_calls[0]["show_alert"] is True


@pytest.mark.asyncio
async def test_handle_referral_reward_choice_success(monkeypatch) -> None:
    monkeypatch.setattr(referral, "SessionLocal", DummySessionLocal())
    emitted_events: list[str] = []

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=42)

    async def _fake_claim(*args, **kwargs):
        return ReferralClaimResult(
            status="CLAIMED",
            reward_code=kwargs["reward_code"],
            overview=_overview(claimable=0),
        )

    async def _fake_invite_link(bot, *, referral_code: str):
        return "https://t.me/testbot?start=ref_ABC123"

    monkeypatch.setattr(referral.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(referral.ReferralService, "claim_next_reward_choice", _fake_claim)
    monkeypatch.setattr(referral, "_build_invite_link", _fake_invite_link)
    async def _fake_emit(*args, **kwargs):
        emitted_events.append(kwargs["event_type"])
        del args, kwargs
        return None

    monkeypatch.setattr(referral, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="referral:reward:MEGA_PACK_15",
        from_user=SimpleNamespace(id=9),
    )
    await referral.handle_referral_reward_choice(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.referral.reward.claimed.megapack"] in (response.text or "")
    assert "https://t.me/" not in (response.text or "")
    assert "referral_reward_claimed" in emitted_events


@pytest.mark.asyncio
async def test_handle_referral_share_opens_share_keyboard(monkeypatch) -> None:
    monkeypatch.setattr(referral, "SessionLocal", DummySessionLocal())
    emitted_events: list[str] = []

    async def _fake_load_overview(*, telegram_user, now_utc):
        del telegram_user, now_utc
        return _overview(claimable=1)

    async def _fake_invite_link(bot, *, referral_code: str):
        del bot, referral_code
        return "https://t.me/testbot?start=ref_ABC123"

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=9)

    monkeypatch.setattr(referral, "_load_overview", _fake_load_overview)
    monkeypatch.setattr(referral, "_build_invite_link", _fake_invite_link)
    monkeypatch.setattr(referral.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    async def _fake_emit(*args, **kwargs):
        emitted_events.append(kwargs["event_type"])
        del args, kwargs
        return None

    monkeypatch.setattr(referral, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(data="referral:share", from_user=SimpleNamespace(id=9))
    await referral.handle_referral_share(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.referral.share.ready"] in (response.text or "")
    urls = [
        button.url for row in response.kwargs["reply_markup"].inline_keyboard for button in row if button.url
    ]
    assert any(url and "https://t.me/share/url" in url for url in urls)
    assert "referral_link_shared" in emitted_events
