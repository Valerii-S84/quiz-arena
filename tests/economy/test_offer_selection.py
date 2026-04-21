from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.economy.offers.template_selection as template_selection
from app.economy.offers.constants import TRG_STREAK_GT7
from app.economy.offers.selection import selection_from_template
from app.economy.offers.types import OfferTemplate
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


class _Session(AsyncSessionStub):
    pass


def _template(*, cta_product_codes: tuple[str, ...]) -> OfferTemplate:
    return OfferTemplate(
        offer_code="OFFER_TEST",
        trigger_code="TRG_TEST",
        priority=10,
        text_key="msg.offer.test",
        cta_product_codes=cta_product_codes,
        blocking_modal=True,
    )


def test_selection_from_template_skips_premium_downgrade_codes_for_active_premium() -> None:
    selection = selection_from_template(
        impression_id=12,
        template=_template(cta_product_codes=("STREAK_SAVER_20", "PREMIUM_MONTH")),
        idempotent_replay=False,
        active_premium_scope="PREMIUM_YEAR",
    )

    assert selection.cta_product_codes == ("STREAK_SAVER_20",)


@pytest.mark.asyncio
async def test_select_template_with_caps_skips_templates_with_only_downgrade_ctas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)
    trigger_codes = {TRG_STREAK_GT7}

    async def _fake_list_for_user_since(*_args, **_kwargs):
        return []

    async def _fake_active_scope(*_args, **_kwargs):
        return "PREMIUM_YEAR"

    monkeypatch.setattr(
        template_selection.OffersRepo,
        "list_for_user_since",
        _fake_list_for_user_since,
    )
    monkeypatch.setattr(
        template_selection.EntitlementsRepo,
        "get_active_premium_scope",
        _fake_active_scope,
    )
    monkeypatch.setattr(template_selection, "has_recent_blocking_modal", lambda **_kwargs: False)
    monkeypatch.setattr(template_selection, "was_offer_shown_recently", lambda **_kwargs: False)
    monkeypatch.setattr(template_selection, "is_offer_muted", lambda **_kwargs: False)
    monkeypatch.setattr(template_selection, "berlin_now", lambda _now_utc: _now_utc)

    selected = await template_selection.select_template_with_caps(
        _Session(),
        user_id=8,
        trigger_codes=trigger_codes,
        now_utc=now_utc,
    )

    assert selected is None
