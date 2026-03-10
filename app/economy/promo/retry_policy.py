from __future__ import annotations

from collections.abc import Sequence

from app.db.models.promo_redemptions import PromoRedemption

ACTIVE_REDEMPTION_STATUSES = frozenset({"VALIDATED", "RESERVED"})
NON_RETRYABLE_REDEMPTION_STATUSES = frozenset({"REJECTED"})


def _is_consumed_redemption(redemption: PromoRedemption) -> bool:
    return (
        redemption.status == "APPLIED"
        or redemption.applied_purchase_id is not None
        or redemption.grant_entitlement_id is not None
    )


def can_user_retry_promo(
    *,
    redemptions: Sequence[PromoRedemption],
    max_uses_per_user: int,
) -> bool:
    """Allows one extra redeem attempt beyond the per-user usage cap."""
    if not redemptions:
        return True

    if any(redemption.status in ACTIVE_REDEMPTION_STATUSES for redemption in redemptions):
        return False

    if any(redemption.status in NON_RETRYABLE_REDEMPTION_STATUSES for redemption in redemptions):
        return False

    consumed_uses = sum(1 for redemption in redemptions if _is_consumed_redemption(redemption))
    if consumed_uses >= max(1, max_uses_per_user):
        return False

    # One extra retry is allowed for expired/canceled reservation flows.
    allowed_total_redemptions = max(1, max_uses_per_user) + 1
    return len(redemptions) < allowed_total_redemptions
