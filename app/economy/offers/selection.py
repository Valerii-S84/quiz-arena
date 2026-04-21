from __future__ import annotations

from app.db.models.offers_impressions import OfferImpression
from app.economy.offers.constants import OFFER_TEMPLATES
from app.economy.offers.eligibility import eligible_cta_product_codes
from app.economy.offers.types import OfferSelection, OfferTemplate


def selection_from_template(
    *,
    impression_id: int,
    template: OfferTemplate,
    idempotent_replay: bool,
    active_premium_scope: str | None = None,
) -> OfferSelection:
    cta_product_codes = eligible_cta_product_codes(
        template.cta_product_codes,
        active_premium_scope=active_premium_scope,
    )
    return OfferSelection(
        impression_id=impression_id,
        offer_code=template.offer_code,
        trigger_code=template.trigger_code,
        priority=template.priority,
        text_key=template.text_key,
        cta_product_codes=cta_product_codes,
        idempotent_replay=idempotent_replay,
    )


def selection_from_impression(
    impression: OfferImpression,
    *,
    idempotent_replay: bool,
    active_premium_scope: str | None = None,
) -> OfferSelection | None:
    template = OFFER_TEMPLATES.get(impression.trigger_code)
    if template is None:
        return None

    selection = selection_from_template(
        impression_id=impression.id,
        template=template,
        idempotent_replay=idempotent_replay,
        active_premium_scope=active_premium_scope,
    )
    if not selection.cta_product_codes:
        return None
    return selection
