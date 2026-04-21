from __future__ import annotations

import structlog
from fastapi import HTTPException, Request

from app.core.config import get_settings as _base_get_settings
from app.db.models.referrals import Referral
from app.services.internal_auth import (
    OPS_UI_SESSION_COOKIE,
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_service_request_authenticated,
)
from app.services.ops_auth import OpsSessionStateError, validate_ops_ui_session

from .internal_referrals_models import ReferralReviewCaseResponse

logger = structlog.get_logger(__name__)


def _get_settings():
    try:
        from app.api.routes import internal_referrals
    except Exception:  # pragma: no cover - defensive fallback
        return _base_get_settings()
    return internal_referrals.get_settings()


def _auth_state_unavailable_http_error() -> HTTPException:
    return HTTPException(status_code=503, detail={"code": "E_AUTH_STATE_UNAVAILABLE"})


async def _assert_ops_surface_access(request: Request) -> None:
    settings = _get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning(
            "internal_referrals_auth_failed",
            reason="ip_not_allowed",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if is_internal_service_request_authenticated(
        request,
        expected_token=settings.internal_api_token,
    ):
        return

    try:
        if await validate_ops_ui_session(
            settings=settings,
            session_id=request.cookies.get(OPS_UI_SESSION_COOKIE),
        ):
            return
    except OpsSessionStateError as exc:
        logger.warning(
            "internal_referrals_auth_failed",
            reason="auth_state_unavailable",
            client_ip=client_ip,
        )
        raise _auth_state_unavailable_http_error() from exc

    logger.warning(
        "internal_referrals_auth_failed",
        reason="invalid_credentials",
        client_ip=client_ip,
    )
    raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


def _as_review_case(referral: Referral) -> ReferralReviewCaseResponse:
    return ReferralReviewCaseResponse(
        referral_id=int(referral.id),
        referrer_user_id=int(referral.referrer_user_id),
        referred_user_id=int(referral.referred_user_id),
        status=str(referral.status),
        fraud_score=float(referral.fraud_score),
        created_at=referral.created_at,
        qualified_at=referral.qualified_at,
        rewarded_at=referral.rewarded_at,
    )
