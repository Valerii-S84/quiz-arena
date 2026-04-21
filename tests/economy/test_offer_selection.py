from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.economy.offers.evaluation as evaluation
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


def test_selection_from_template_blocks_unknown_premium_scope_from_premium_ctas() -> None:
    selection = selection_from_template(
        impression_id=13,
        template=_template(cta_product_codes=("STREAK_SAVER_20", "PREMIUM_MONTH")),
        idempotent_replay=False,
        active_premium_scope="ADMIN_BONUS",
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

    async def _unexpected_active_scope(*_args, **_kwargs):
        raise AssertionError("expected template selection to reuse provided premium scope snapshot")

    monkeypatch.setattr(
        template_selection.OffersRepo,
        "list_for_user_since",
        _fake_list_for_user_since,
    )
    monkeypatch.setattr(
        template_selection.EntitlementsRepo,
        "get_active_premium_scope",
        _unexpected_active_scope,
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
        active_premium_scope="PREMIUM_YEAR",
        resolve_active_premium_scope=False,
    )

    assert selected is None


@pytest.mark.asyncio
async def test_evaluate_and_log_offer_reuses_active_premium_scope_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)
    selected_scope: dict[str, str | None] = {}

    async def _fake_active_scope(*_args, **_kwargs):
        return "ADMIN_BONUS"

    async def _fake_get_by_idempotency_key(*_args, **_kwargs):
        return None

    async def _fake_build_trigger_codes(*_args, **_kwargs):
        return {TRG_STREAK_GT7}

    async def _fake_select_template_with_caps(*_args, active_premium_scope, **_kwargs):
        selected_scope["value"] = active_premium_scope
        return _template(cta_product_codes=("STREAK_SAVER_20", "PREMIUM_MONTH"))

    async def _fake_insert_impression_if_absent(*_args, **_kwargs):
        return 42

    monkeypatch.setattr(
        evaluation.EntitlementsRepo,
        "get_active_premium_scope",
        _fake_active_scope,
    )
    monkeypatch.setattr(
        evaluation.OffersRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(evaluation, "build_trigger_codes", _fake_build_trigger_codes)
    monkeypatch.setattr(
        evaluation,
        "select_template_with_caps",
        _fake_select_template_with_caps,
    )
    monkeypatch.setattr(
        evaluation.OffersRepo,
        "insert_impression_if_absent",
        _fake_insert_impression_if_absent,
    )
    monkeypatch.setattr(evaluation, "berlin_now", lambda _now_utc: _now_utc)

    selection = await evaluation.evaluate_and_log_offer(
        _Session(),
        user_id=8,
        idempotency_key="offer-scope-snapshot",
        now_utc=now_utc,
    )

    assert selected_scope["value"] == "ADMIN_BONUS"
    assert selection is not None
    assert selection.cta_product_codes == ("STREAK_SAVER_20",)
