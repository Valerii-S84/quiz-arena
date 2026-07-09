from __future__ import annotations

import hashlib
import json

import structlog

from app.db.repo.payment_inbox_repo import PaymentEventsRepo, TelegramUpdateInboxRepo
from app.db.session import SessionLocal

logger = structlog.get_logger(__name__)

PAYMENT_UPDATE_KIND_PRE_CHECKOUT = "pre_checkout_query"
PAYMENT_UPDATE_KIND_SUCCESSFUL = "message.successful_payment"
PAYMENT_UPDATE_KIND_REFUNDED = "message.refunded_payment"
PAYMENT_EVENT_TYPES = {
    PAYMENT_UPDATE_KIND_PRE_CHECKOUT: "PRE_CHECKOUT",
    PAYMENT_UPDATE_KIND_SUCCESSFUL: "SUCCESSFUL_PAYMENT",
    PAYMENT_UPDATE_KIND_REFUNDED: "REFUNDED_PAYMENT",
}


async def store_payment_update_evidence(
    *,
    update_payload: dict[str, object],
    update_id: int,
) -> bool:
    payment_update_kind = payment_update_kind_for_update(update_payload)
    if payment_update_kind is None:
        return True

    evidence = sanitized_payment_update_evidence(
        update_payload=update_payload,
        update_id=update_id,
        payment_update_kind=payment_update_kind,
    )
    try:
        async with SessionLocal.begin() as session:
            inbox, _ = await TelegramUpdateInboxRepo.create_once(
                session,
                update_id=update_id,
                update_kind=payment_update_kind,
                idempotency_key=str(evidence["payment_update_key"]),
                payload_hash=_safe_payload_hash(evidence),
                sanitized_evidence=evidence,
            )
            await PaymentEventsRepo.create_once(
                session,
                provider="TELEGRAM",
                event_type=PAYMENT_EVENT_TYPES[payment_update_kind],
                idempotency_key=str(evidence["payment_update_key"]),
                source_inbox_update_id=inbox.update_id,
                invoice_payload=_optional_str(evidence.get("invoice_payload")),
                provider_charge_id_hash=_optional_str(
                    evidence.get("telegram_payment_charge_id_hash")
                ),
                provider_payment_charge_id_hash=_optional_str(
                    evidence.get("provider_payment_charge_id_hash")
                ),
                currency=_optional_str(evidence.get("currency")),
                total_amount=_optional_int(evidence.get("total_amount")),
                telegram_user_id=_optional_int(evidence.get("telegram_user_id")),
                safe_payload=evidence,
            )
    except Exception as exc:
        logger.warning(
            "telegram_payment_update_evidence_store_failed",
            update_id=update_id,
            payment_update_kind=payment_update_kind,
            error_type=type(exc).__name__,
        )
        return False
    return True


def payment_update_kind_for_update(update_payload: dict[str, object]) -> str | None:
    if isinstance(update_payload.get("pre_checkout_query"), dict):
        return PAYMENT_UPDATE_KIND_PRE_CHECKOUT

    message = update_payload.get("message")
    if not isinstance(message, dict):
        return None
    if isinstance(message.get("successful_payment"), dict):
        return PAYMENT_UPDATE_KIND_SUCCESSFUL
    if isinstance(message.get("refunded_payment"), dict):
        return PAYMENT_UPDATE_KIND_REFUNDED
    return None


def sanitized_payment_update_evidence(
    *,
    update_payload: dict[str, object],
    update_id: int,
    payment_update_kind: str,
) -> dict[str, object]:
    payment_payload = _payment_payload_for_kind(update_payload, payment_update_kind)
    evidence: dict[str, object | None] = {
        "schema_version": 1,
        "source": "telegram_webhook",
        "update_id": update_id,
        "payment_update_kind": payment_update_kind,
        "payment_update_key": f"telegram:{update_id}:{payment_update_kind}",
        "invoice_payload": _safe_str(payment_payload.get("invoice_payload")),
        "currency": _safe_str(payment_payload.get("currency")),
        "total_amount": _safe_int(payment_payload.get("total_amount")),
        "telegram_user_id": _payment_update_user_id(update_payload, payment_update_kind),
        "message_id": _payment_update_message_id(update_payload, payment_update_kind),
        "telegram_payment_charge_id_hash": _hash_payment_identifier(
            payment_payload.get("telegram_payment_charge_id")
        ),
        "provider_payment_charge_id_hash": _hash_payment_identifier(
            payment_payload.get("provider_payment_charge_id")
        ),
        "order_info_present": isinstance(payment_payload.get("order_info"), dict),
        "raw_payload_stored": False,
    }
    return {key: value for key, value in evidence.items() if value is not None}


def _payment_payload_for_kind(
    update_payload: dict[str, object],
    payment_update_kind: str,
) -> dict[str, object]:
    if payment_update_kind == PAYMENT_UPDATE_KIND_PRE_CHECKOUT:
        value = update_payload.get("pre_checkout_query")
        return value if isinstance(value, dict) else {}

    message = update_payload.get("message")
    if not isinstance(message, dict):
        return {}
    field_name = payment_update_kind.removeprefix("message.")
    value = message.get(field_name)
    return value if isinstance(value, dict) else {}


def _payment_update_user_id(
    update_payload: dict[str, object],
    payment_update_kind: str,
) -> int | None:
    container: object
    if payment_update_kind == PAYMENT_UPDATE_KIND_PRE_CHECKOUT:
        container = update_payload.get("pre_checkout_query")
    else:
        container = update_payload.get("message")
    if not isinstance(container, dict):
        return None
    from_user = container.get("from")
    if not isinstance(from_user, dict):
        return None
    return _safe_int(from_user.get("id"))


def _payment_update_message_id(
    update_payload: dict[str, object],
    payment_update_kind: str,
) -> int | None:
    if not payment_update_kind.startswith("message."):
        return None
    message = update_payload.get("message")
    if not isinstance(message, dict):
        return None
    return _safe_int(message.get("message_id"))


def _safe_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _safe_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _hash_payment_identifier(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_payload_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
