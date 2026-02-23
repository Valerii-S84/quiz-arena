from __future__ import annotations

import structlog
from fastapi import HTTPException, Request

from app.core.config import get_settings as _base_get_settings
from app.economy.promo.types import PromoRedeemResult
from app.services.internal_auth import (
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_request_authenticated,
)

from .internal_promo_models import PromoCampaignResponse, PromoRedeemResponse

logger = structlog.get_logger(__name__)


def _get_settings():
    try:
        from app.api.routes import internal_promo
    except Exception:  # pragma: no cover - defensive fallback
        return _base_get_settings()
    return internal_promo.get_settings()


def _as_response(result: PromoRedeemResult) -> PromoRedeemResponse:
    return PromoRedeemResponse(
        redemption_id=result.redemption_id,
        result_type=result.result_type,
        premium_days=result.premium_days,
        premium_ends_at=result.premium_ends_at,
        discount_percent=result.discount_percent,
        reserved_until=result.reserved_until,
        target_scope=result.target_scope,
    )


def _campaign_as_response(campaign: object) -> PromoCampaignResponse:
    return PromoCampaignResponse(
        id=int(getattr(campaign, "id")),
        campaign_name=str(getattr(campaign, "campaign_name")),
        promo_type=str(getattr(campaign, "promo_type")),
        target_scope=str(getattr(campaign, "target_scope")),
        status=str(getattr(campaign, "status")),
        valid_from=getattr(campaign, "valid_from"),
        valid_until=getattr(campaign, "valid_until"),
        max_total_uses=getattr(campaign, "max_total_uses"),
        used_total=int(getattr(campaign, "used_total")),
        updated_at=getattr(campaign, "updated_at"),
    )


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _assert_internal_access(request: Request) -> None:
    settings = _get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("internal_promo_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if not is_internal_request_authenticated(
        request,
        expected_token=settings.internal_api_token,
    ):
        logger.warning(
            "internal_promo_auth_failed",
            reason="invalid_credentials",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
