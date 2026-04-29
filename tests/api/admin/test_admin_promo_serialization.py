from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.api.routes.admin.promo_models import OPEN_ENDED_VALID_UNTIL, serialize_promo
from app.api.routes.admin.promo_serialization import (
    effective_applicable_products,
    resolve_display_status,
)
from tests.type_helpers import build_promo_code

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def _promo(**overrides: object):
    payload: dict[str, object] = {
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=1),
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(hours=1),
    }
    payload.update(overrides)
    return build_promo_code(**payload)


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"status": "PAUSED"}, "inactive"),
        ({"status": "EXPIRED"}, "expired"),
        ({"status": "DEPLETED"}, "expired"),
        ({"valid_until": NOW}, "expired"),
        ({"max_total_uses": 5, "used_total": 5}, "expired"),
        ({}, "active"),
    ],
)
def test_resolve_display_status_handles_terminal_and_capacity_states(
    overrides: dict[str, object],
    status: str,
) -> None:
    assert resolve_display_status(_promo(**overrides), now_utc=NOW) == status


@pytest.mark.parametrize(
    ("overrides", "products"),
    [
        ({"applicable_products": ["energy_10", 42]}, ["energy_10", "42"]),
        ({"target_scope": "ENERGY_10"}, ["ENERGY_10"]),
        ({"target_scope": "MICRO_ANY"}, None),
        ({"target_scope": "PREMIUM_ANY"}, None),
        ({"target_scope": "MULTI"}, None),
    ],
)
def test_effective_applicable_products_resolves_stored_and_legacy_scopes(
    overrides: dict[str, object],
    products: list[str] | None,
) -> None:
    assert effective_applicable_products(_promo(**overrides)) == products


def test_serialize_promo_masks_code_and_keeps_open_ended_validity_hidden() -> None:
    promo = _promo(
        code_prefix="SPRING",
        code_encrypted=b"ciphertext",
        valid_until=OPEN_ENDED_VALID_UNTIL,
        max_total_uses=None,
        used_total=2,
        target_scope="ENERGY_10",
    )

    payload = serialize_promo(promo, raw_code="SPRING2026", can_reveal_code=True, now_utc=NOW)

    assert payload["code"] == "SPRING****"
    assert payload["raw_code"] == "SPRING2026"
    assert payload["can_reveal_code"] is True
    assert payload["valid_until"] is None
    assert payload["max_total_uses"] == 0
    assert payload["max_uses"] == 0
    assert payload["product_id"] == "ENERGY_10"
    assert payload["status"] == "active"


def test_serialize_premium_grant_uses_legacy_grant_shape() -> None:
    promo = _promo(
        promo_type="PREMIUM_GRANT",
        grant_premium_days=30,
        discount_type=None,
        discount_value=None,
        discount_percent=None,
        target_scope="PREMIUM_ANY",
    )

    payload = serialize_promo(promo, can_reveal_code=True, now_utc=NOW)

    assert payload["discount_type"] is None
    assert payload["discount_value"] == 30
    assert payload["type"] == "bonus_subscription_days"
    assert payload["value"] == 30
    assert payload["applicable_products"] is None
    assert payload["can_reveal_code"] is False
