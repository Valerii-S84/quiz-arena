from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.services.promo_codes import hash_promo_code, normalize_promo_code

from .promo_models import (
    OPEN_ENDED_VALID_UNTIL,
    PromoBulkCreateRequest,
    PromoCreateRequest,
    PromoPatchRequest,
    resolve_applicable_products,
    resolve_discount_type,
    resolve_discount_value,
    resolve_max_total_uses,
    resolve_promo_type,
    resolve_target_scope,
    serialize_promo,
)

PromoMutationRequest = PromoCreateRequest | PromoBulkCreateRequest | PromoPatchRequest


def code_hash_from_raw(raw_code: str) -> str:
    return hash_promo_code(
        normalized_code=normalize_promo_code(raw_code),
        pepper=get_settings().promo_secret_pepper,
    )


def resolve_discount_fields(
    *,
    promo_type: str,
    discount_type: str | None,
    discount_value: int | None,
) -> tuple[str | None, int | None, int | None, int | None]:
    if promo_type == "PREMIUM_GRANT":
        if discount_value not in {7, 30, 90}:
            raise HTTPException(status_code=422, detail={"code": "E_PROMO_DISCOUNT_VALUE_INVALID"})
        return None, None, None, discount_value

    resolved_type = discount_type or "PERCENT"
    if resolved_type == "FREE":
        return "FREE", None, 100, None
    if discount_value is None:
        raise HTTPException(status_code=422, detail={"code": "E_PROMO_DISCOUNT_VALUE_REQUIRED"})
    if resolved_type == "PERCENT" and not 1 <= discount_value <= 100:
        raise HTTPException(status_code=422, detail={"code": "E_PROMO_DISCOUNT_VALUE_INVALID"})
    return (
        resolved_type,
        discount_value,
        discount_value if resolved_type == "PERCENT" else None,
        None,
    )


def campaign_name(raw_value: str | None, *, fallback: str) -> str:
    value = (raw_value or "").strip()
    return value or fallback


def promo_details(promo: PromoCode) -> dict[str, object]:
    serialized = serialize_promo(promo)
    return {
        "campaign_name": serialized["campaign_name"],
        "discount_type": serialized["discount_type"],
        "discount_value": serialized["discount_value"],
        "applicable_products": serialized["applicable_products"] or [],
        "valid_from": serialized["valid_from"],
        "valid_until": serialized["valid_until"],
        "max_total_uses": serialized["max_total_uses"],
        "max_per_user": serialized["max_per_user"],
    }


def apply_mutation_payload(
    *,
    promo: PromoCode,
    payload: PromoMutationRequest,
    now_utc: datetime,
) -> None:
    fields_set = payload.model_fields_set
    promo_type = promo.promo_type
    if "type" in fields_set:
        promo_type = resolve_promo_type(payload.type)

    discount_fields_supplied = bool(
        {"discount_type", "discount_value", "value", "type"} & fields_set
    )
    if discount_fields_supplied:
        discount_type, discount_value, discount_percent, grant_days = resolve_discount_fields(
            promo_type=promo_type,
            discount_type=resolve_discount_type(payload),
            discount_value=resolve_discount_value(payload),
        )
        promo.promo_type = promo_type
        promo.discount_type = discount_type
        promo.discount_value = discount_value
        promo.discount_percent = discount_percent
        promo.grant_premium_days = grant_days

    if "campaign_name" in fields_set:
        promo.campaign_name = campaign_name(payload.campaign_name, fallback=promo.campaign_name)
    if {"applicable_products", "product_id"} & fields_set:
        applicable_products = resolve_applicable_products(payload)
        promo.applicable_products = applicable_products
        promo.target_scope = resolve_target_scope(
            promo_type=promo.promo_type,
            applicable_products=applicable_products,
        )
    if "valid_from" in fields_set:
        promo.valid_from = payload.valid_from or promo.valid_from
    if "valid_until" in fields_set:
        promo.valid_until = payload.valid_until or OPEN_ENDED_VALID_UNTIL
    if {"max_total_uses", "max_uses"} & fields_set:
        promo.max_total_uses = resolve_max_total_uses(payload)
    if "max_per_user" in fields_set and payload.max_per_user is not None:
        promo.max_uses_per_user = payload.max_per_user
    promo.updated_at = now_utc
