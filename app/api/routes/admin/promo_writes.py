from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.api.routes.admin.deps import AdminPrincipal
from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.db.repo.promo_repo_admin_runtime import AdminRuntimePromoRepo
from app.db.session import SessionLocal
from app.services.promo_codes import hash_promo_code, normalize_promo_code
from app.services.promo_encryption import encrypt_promo_code

from .promo_audit import write_promo_audit
from .promo_models import (
    OPEN_ENDED_VALID_UNTIL,
    PromoBulkCreateRequest,
    PromoCreateRequest,
    PromoPatchRequest,
    PromoRevokeRequest,
    build_generated_codes,
    build_promo_id,
    normalized_code,
    raw_code_value,
    resolve_applicable_products,
    resolve_discount_type,
    resolve_discount_value,
    resolve_max_total_uses,
    resolve_promo_type,
    resolve_target_scope,
    serialize_promo,
)


def _code_hash(raw_code: str) -> str:
    return hash_promo_code(
        normalized_code=normalize_promo_code(raw_code),
        pepper=get_settings().promo_secret_pepper,
    )


def _resolve_discount_fields(
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


def _campaign_name(raw_value: str | None, *, fallback: str) -> str:
    value = (raw_value or "").strip()
    return value or fallback


def _promo_details(promo: PromoCode) -> dict[str, object]:
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


def _apply_mutation_payload(
    *,
    promo: PromoCode,
    payload: PromoCreateRequest | PromoBulkCreateRequest | PromoPatchRequest,
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
        discount_type, discount_value, discount_percent, grant_days = _resolve_discount_fields(
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
        promo.campaign_name = _campaign_name(payload.campaign_name, fallback=promo.campaign_name)
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


async def create_promo(*, payload: PromoCreateRequest, admin: AdminPrincipal) -> dict[str, object]:
    raw_code = raw_code_value(payload.code)
    code_hash = _code_hash(raw_code)
    now_utc = datetime.now(timezone.utc)
    try:
        code_encrypted = encrypt_promo_code(raw_code)
    except ValueError as exc:
        raise HTTPException(
            status_code=500, detail={"code": "E_PROMO_ENCRYPTION_UNAVAILABLE"}
        ) from exc

    async with SessionLocal.begin() as session:
        if await AdminRuntimePromoRepo.get_by_hash(session, code_hash) is not None:
            raise HTTPException(status_code=409, detail={"code": "E_PROMO_CODE_EXISTS"})

        promo = PromoCode(
            id=build_promo_id(),
            code_hash=code_hash,
            code_prefix=normalized_code(raw_code)[:8] or "PROMO",
            code_encrypted=code_encrypted,
            campaign_name=_campaign_name(payload.campaign_name, fallback=normalized_code(raw_code)),
            promo_type="PERCENT_DISCOUNT",
            grant_premium_days=None,
            discount_percent=None,
            discount_type=None,
            discount_value=None,
            applicable_products=None,
            target_scope="ANY",
            status="ACTIVE",
            valid_from=payload.valid_from or now_utc,
            valid_until=payload.valid_until or OPEN_ENDED_VALID_UNTIL,
            max_total_uses=None,
            used_total=0,
            max_uses_per_user=max(payload.max_per_user, 1),
            new_users_only=False,
            first_purchase_only=False,
            created_by=admin.email,
            created_at=now_utc,
            updated_at=now_utc,
        )
        _apply_mutation_payload(promo=promo, payload=payload, now_utc=now_utc)
        created = await AdminRuntimePromoRepo.create(session, promo=promo)
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="CREATE",
            promo_code_id=created.id,
            details=_promo_details(created),
        )
    return serialize_promo(created, raw_code=raw_code, can_reveal_code=admin.is_super_admin)


async def create_bulk_promos(
    *,
    payload: PromoBulkCreateRequest,
    admin: AdminPrincipal,
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    prefix = payload.prefix or ""

    async with SessionLocal.begin() as session:
        codes: list[str] = []
        hashes: list[str] = []
        while len(codes) < payload.count:
            missing = payload.count - len(codes)
            batch = build_generated_codes(prefix=prefix, count=missing)
            batch_hashes = [_code_hash(item) for item in batch]
            existing_hashes = await AdminRuntimePromoRepo.list_existing_hashes(
                session,
                code_hashes=batch_hashes,
            )
            for raw_code, code_hash in zip(batch, batch_hashes, strict=True):
                if code_hash in existing_hashes or code_hash in hashes:
                    continue
                codes.append(raw_code)
                hashes.append(code_hash)

        promos: list[PromoCode] = []
        for raw_code, code_hash in zip(codes, hashes, strict=True):
            promo = PromoCode(
                id=build_promo_id(),
                code_hash=code_hash,
                code_prefix=normalized_code(raw_code)[:8] or "PROMO",
                code_encrypted=encrypt_promo_code(raw_code),
                campaign_name=_campaign_name(payload.campaign_name, fallback=prefix or "PROMO"),
                promo_type="PERCENT_DISCOUNT",
                grant_premium_days=None,
                discount_percent=None,
                discount_type=None,
                discount_value=None,
                applicable_products=None,
                target_scope="ANY",
                status="ACTIVE",
                valid_from=payload.valid_from or now_utc,
                valid_until=payload.valid_until or OPEN_ENDED_VALID_UNTIL,
                max_total_uses=None,
                used_total=0,
                max_uses_per_user=max(payload.max_per_user, 1),
                new_users_only=False,
                first_purchase_only=False,
                created_by=admin.email,
                created_at=now_utc,
                updated_at=now_utc,
            )
            _apply_mutation_payload(promo=promo, payload=payload, now_utc=now_utc)
            promos.append(promo)

        created = await AdminRuntimePromoRepo.bulk_create(session, promos=promos)
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="BULK_GENERATE",
            promo_code_id=None,
            details={"count": len(created)},
        )
    return {
        "generated": len(created),
        "codes": codes,
        "count": len(created),
        "items": [
            serialize_promo(promo, raw_code=raw_code, can_reveal_code=admin.is_super_admin)
            for promo, raw_code in zip(created, codes, strict=True)
        ],
    }


async def patch_promo(
    *, promo_id: int, payload: PromoPatchRequest, admin: AdminPrincipal
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id_for_update(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        _apply_mutation_payload(promo=promo, payload=payload, now_utc=now_utc)
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="UPDATE",
            promo_code_id=promo.id,
            details=_promo_details(promo),
        )
    return serialize_promo(promo, can_reveal_code=admin.is_super_admin)


async def toggle_promo(*, promo_id: int, admin: AdminPrincipal) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id_for_update(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        if promo.status not in {"ACTIVE", "PAUSED"}:
            raise HTTPException(status_code=409, detail={"code": "E_PROMO_STATUS_CONFLICT"})
        promo.status = "PAUSED" if promo.status == "ACTIVE" else "ACTIVE"
        promo.updated_at = now_utc
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="DEACTIVATE" if promo.status == "PAUSED" else "ACTIVATE",
            promo_code_id=promo.id,
            details={"status": promo.status},
        )
    return serialize_promo(promo, can_reveal_code=admin.is_super_admin)


async def revoke_promo(
    *,
    promo_id: int,
    payload: PromoRevokeRequest | None,
    admin: AdminPrincipal,
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    revoke_reason = payload.reason.strip() if payload is not None and payload.reason else ""
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id_for_update(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        revoked = await AdminRuntimePromoRepo.revoke_active_reserved_redemptions(
            session,
            promo_id=promo.id,
            now_utc=now_utc,
        )
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="REVOKE",
            promo_code_id=promo.id,
            details={
                "revoked_count": len(revoked),
                "reason": revoke_reason or None,
            },
        )
    return {
        "promo": serialize_promo(promo),
        "revoked_count": len(revoked),
        "reason": revoke_reason or None,
    }
