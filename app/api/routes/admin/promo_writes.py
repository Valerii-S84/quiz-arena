from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.api.routes.admin.deps import AdminPrincipal
from app.db.models.promo_codes import PromoCode
from app.db.repo.promo_repo_admin_runtime import AdminRuntimePromoRepo
from app.db.session import SessionLocal
from app.services.promo_encryption import encrypt_promo_code

from .promo_audit import write_promo_audit
from .promo_models import (
    OPEN_ENDED_VALID_UNTIL,
    PromoBulkCreateRequest,
    PromoCreateRequest,
    PromoPatchRequest,
    build_generated_codes,
    build_promo_id,
    normalized_code,
    raw_code_value,
    serialize_promo,
)
from .promo_write_helpers import (
    apply_mutation_payload,
    campaign_name,
    code_hash_from_raw,
    promo_details,
)


async def create_promo(*, payload: PromoCreateRequest, admin: AdminPrincipal) -> dict[str, object]:
    raw_code = raw_code_value(payload.code)
    code_hash = code_hash_from_raw(raw_code)
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
            campaign_name=campaign_name(payload.campaign_name, fallback=normalized_code(raw_code)),
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
        apply_mutation_payload(promo=promo, payload=payload, now_utc=now_utc)
        created = await AdminRuntimePromoRepo.create(session, promo=promo)
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="CREATE",
            promo_code_id=created.id,
            details=promo_details(created),
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
            batch_hashes = [code_hash_from_raw(item) for item in batch]
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
                campaign_name=campaign_name(payload.campaign_name, fallback=prefix or "PROMO"),
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
            apply_mutation_payload(promo=promo, payload=payload, now_utc=now_utc)
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
        apply_mutation_payload(promo=promo, payload=payload, now_utc=now_utc)
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="UPDATE",
            promo_code_id=promo.id,
            details=promo_details(promo),
        )
    return serialize_promo(promo, can_reveal_code=admin.is_super_admin)
