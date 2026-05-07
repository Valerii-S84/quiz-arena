from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.routes.admin.promo_models import OPEN_ENDED_VALID_UNTIL, PromoPatchRequest
from app.api.routes.admin.promo_write_helpers import (
    apply_mutation_payload,
    campaign_name,
    promo_details,
    resolve_discount_fields,
    resolve_max_total_uses,
)
from tests.type_helpers import build_promo_code

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def _promo(**overrides: object):
    payload = {
        "campaign_name": "Existing",
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=1),
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(hours=1),
    }
    payload.update(overrides)
    return build_promo_code(**payload)


@pytest.mark.parametrize(
    ("promo_type", "discount_type", "discount_value", "expected"),
    [
        ("PERCENT_DISCOUNT", "FREE", None, ("FREE", None, 100, None)),
        ("PERCENT_DISCOUNT", None, 25, ("PERCENT", 25, 25, None)),
        ("PERCENT_DISCOUNT", "FIXED", 50, ("FIXED", 50, None, None)),
        ("PREMIUM_GRANT", None, 30, (None, None, None, 30)),
    ],
)
def test_resolve_discount_fields_accepts_supported_shapes(
    promo_type: str,
    discount_type: str | None,
    discount_value: int | None,
    expected: tuple[str | None, int | None, int | None, int | None],
) -> None:
    assert (
        resolve_discount_fields(
            promo_type=promo_type,
            discount_type=discount_type,
            discount_value=discount_value,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("promo_type", "discount_type", "discount_value"),
    [
        ("PERCENT_DISCOUNT", "PERCENT", None),
        ("PERCENT_DISCOUNT", "PERCENT", 101),
        ("PREMIUM_GRANT", None, 14),
    ],
)
def test_resolve_discount_fields_rejects_invalid_values(
    promo_type: str,
    discount_type: str | None,
    discount_value: int | None,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_discount_fields(
            promo_type=promo_type,
            discount_type=discount_type,
            discount_value=discount_value,
        )

    assert exc_info.value.status_code == 422


def test_apply_mutation_payload_updates_only_supplied_patch_fields() -> None:
    promo = _promo(max_total_uses=10, max_uses_per_user=1)
    payload = PromoPatchRequest(
        campaign_name="  ",
        discount_type="FREE",
        applicable_products=[" energy_10 ", "ENERGY_10", "premium_month"],
        valid_from=NOW,
        valid_until=None,
        max_total_uses=0,
        max_per_user=3,
    )

    apply_mutation_payload(promo=promo, payload=payload, now_utc=NOW)

    assert promo.campaign_name == "Existing"
    assert promo.discount_type == "FREE"
    assert promo.discount_percent == 100
    assert promo.applicable_products == ["ENERGY_10", "PREMIUM_MONTH"]
    assert promo.target_scope == "MULTI"
    assert promo.valid_from == NOW
    assert promo.valid_until == OPEN_ENDED_VALID_UNTIL
    assert promo.max_total_uses is None
    assert promo.max_uses_per_user == 3
    assert promo.updated_at == NOW


def test_apply_mutation_payload_supports_legacy_premium_grant_patch() -> None:
    promo = _promo()
    payload = PromoPatchRequest(type="bonus_subscription_days", value=90)

    apply_mutation_payload(promo=promo, payload=payload, now_utc=NOW)

    assert promo.promo_type == "PREMIUM_GRANT"
    assert promo.discount_type is None
    assert promo.discount_value is None
    assert promo.discount_percent is None
    assert promo.grant_premium_days == 90
    assert promo.target_scope == "ANY"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (PromoPatchRequest(max_total_uses=0), None),
        (PromoPatchRequest(max_total_uses=5), 5),
        (PromoPatchRequest(max_uses=0), None),
        (PromoPatchRequest(max_uses=9), 9),
    ],
)
def test_resolve_max_total_uses_handles_zero_and_legacy_alias(
    payload: PromoPatchRequest,
    expected: int | None,
) -> None:
    assert resolve_max_total_uses(payload) == expected


def test_write_helpers_build_fallback_name_and_audit_details() -> None:
    promo = _promo(
        campaign_name="Spring",
        discount_type="FIXED",
        discount_value=50,
        discount_percent=None,
        applicable_products=["PREMIUM_MONTH"],
        max_total_uses=None,
    )

    assert campaign_name("  ", fallback="Fallback") == "Fallback"
    assert promo_details(promo) == {
        "campaign_name": "Spring",
        "discount_type": "FIXED",
        "discount_value": 50,
        "applicable_products": ["PREMIUM_MONTH"],
        "valid_from": promo.valid_from.isoformat(),
        "valid_until": promo.valid_until.isoformat(),
        "max_total_uses": 0,
        "max_per_user": 1,
    }
