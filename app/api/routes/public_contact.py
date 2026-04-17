from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.db.models.contact_requests import ContactRequest as ContactRequestModel
from app.db.session import SessionLocal
from app.services.contact_rate_limit import (
    ContactRateLimitStateError,
    consume_contact_submission_slot,
)
from app.services.internal_auth import extract_client_ip

from .public_contact_payload import (
    ContactPayload,
    is_honeypot_triggered,
    normalize_contact_payload,
    validate_contact_payload,
)

router = APIRouter(tags=["public-site"])
logger = structlog.get_logger(__name__)

CONTACT_RATE_LIMIT_ATTEMPTS = 5
CONTACT_RATE_LIMIT_WINDOW_SECONDS = 10 * 60


def _contact_rate_limit_bucket(request: Request, settings: Settings) -> tuple[str, str | None]:
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )
    return f"contact:ip:{client_ip or 'unknown'}", client_ip


# Keep both paths for compatibility:
# - direct API calls use /api/contact
# - reverse-proxy setups with stripped /api prefix use /contact
@router.post("/contact", status_code=status.HTTP_202_ACCEPTED)
@router.post("/api/contact", status_code=status.HTTP_202_ACCEPTED)
async def submit_contact(
    payload: ContactPayload,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    bucket, client_ip = _contact_rate_limit_bucket(request, settings)
    try:
        is_rate_limited = await consume_contact_submission_slot(
            settings=settings,
            bucket=bucket,
            limit=CONTACT_RATE_LIMIT_ATTEMPTS,
            window_seconds=CONTACT_RATE_LIMIT_WINDOW_SECONDS,
        )
    except ContactRateLimitStateError as exc:
        logger.warning(
            "public_contact_guard_unavailable",
            reason="rate_limit_state_unavailable",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=503, detail={"code": "E_RATE_LIMIT_UNAVAILABLE"}) from exc

    if is_rate_limited:
        logger.warning(
            "public_contact_rejected",
            reason="rate_limited",
            client_ip=client_ip,
            request_type=payload.request_type,
        )
        raise HTTPException(status_code=429, detail={"code": "E_RATE_LIMITED"})

    if is_honeypot_triggered(payload):
        logger.warning(
            "public_contact_rejected",
            reason="honeypot_triggered",
            client_ip=client_ip,
            request_type=payload.request_type,
        )
        return {"ok": True}

    validate_contact_payload(payload)
    normalized_payload = normalize_contact_payload(payload)

    async with SessionLocal.begin() as session:
        session.add(
            ContactRequestModel(
                request_type=payload.request_type,
                name=payload.name.strip(),
                contact=payload.contact.strip(),
                payload=normalized_payload,
            )
        )

    # TODO: Forward saved contact requests to CRM/Telegram notification channel.
    return {"ok": True}
