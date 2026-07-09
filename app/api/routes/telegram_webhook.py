from __future__ import annotations

import asyncio
import hashlib

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.session import SessionLocal
from app.services.telegram_updates import extract_update_id, is_valid_webhook_secret
from app.workers.tasks.telegram_updates import process_telegram_update

router = APIRouter(tags=["telegram"])
logger = structlog.get_logger(__name__)
PAYMENT_UPDATE_EVIDENCE_EVENT = "telegram_payment_update_received"


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


async def _enqueue_update(
    *,
    update_payload: dict[str, object],
    update_id: int,
    timeout_seconds: float,
) -> bool:
    def enqueue_call() -> object:
        return process_telegram_update.delay(
            update_payload=update_payload,
            update_id=update_id,
        )

    try:
        if _is_celery_task(process_telegram_update):
            await asyncio.wait_for(
                asyncio.to_thread(enqueue_call),
                timeout=timeout_seconds,
            )
        else:
            enqueue_call()
        return True
    except asyncio.TimeoutError:
        logger.warning(
            "telegram_webhook_enqueue_timeout",
            update_id=update_id,
            enqueue_timeout_seconds=timeout_seconds,
        )
        return False
    except Exception as exc:
        logger.warning(
            "telegram_webhook_enqueue_failed",
            update_id=update_id,
            error_type=type(exc).__name__,
        )
        return False


def _payment_update_kind(update_payload: dict[str, object]) -> str | None:
    if isinstance(update_payload.get("pre_checkout_query"), dict):
        return "pre_checkout_query"

    message = update_payload.get("message")
    if not isinstance(message, dict):
        return None
    if isinstance(message.get("successful_payment"), dict):
        return "message.successful_payment"
    if isinstance(message.get("refunded_payment"), dict):
        return "message.refunded_payment"
    return None


async def _store_payment_update_evidence(
    *,
    update_payload: dict[str, object],
    update_id: int,
) -> bool:
    payment_update_kind = _payment_update_kind(update_payload)
    if payment_update_kind is None:
        return True

    payload = _sanitized_payment_update_evidence(
        update_payload=update_payload,
        update_id=update_id,
        payment_update_kind=payment_update_kind,
    )
    try:
        async with SessionLocal.begin() as session:
            await OutboxEventsRepo.create_once_by_payload_key(
                session,
                event_type=PAYMENT_UPDATE_EVIDENCE_EVENT,
                payload=payload,
                payload_key="payment_update_key",
                status="PENDING",
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


def _sanitized_payment_update_evidence(
    *,
    update_payload: dict[str, object],
    update_id: int,
    payment_update_kind: str,
) -> dict[str, object]:
    payment_payload = _payment_payload_for_kind(update_payload, payment_update_kind)
    evidence: dict[str, object | None] = {
        "schema_version": 1,
        "update_id": update_id,
        "payment_update_kind": payment_update_kind,
        "payment_update_key": f"{update_id}:{payment_update_kind}",
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
    if payment_update_kind == "pre_checkout_query":
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
    if payment_update_kind == "pre_checkout_query":
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


def _hash_payment_identifier(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request) -> JSONResponse:
    settings = get_settings()
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not is_valid_webhook_secret(
        expected_secret=settings.telegram_webhook_secret,
        received_secret=received_secret,
    ):
        logger.warning("telegram_webhook_invalid_secret")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ignored"},
        )

    try:
        update_payload = await request.json()
    except Exception:
        logger.warning("telegram_webhook_invalid_json")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ignored"},
        )

    update_id = extract_update_id(update_payload)
    if update_id is None:
        logger.warning("telegram_webhook_missing_update_id")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ignored"},
        )

    evidence_stored = await _store_payment_update_evidence(
        update_payload=update_payload,
        update_id=update_id,
    )
    if not evidence_stored:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "retry"},
        )

    enqueue_timeout_ms = max(
        1,
        int(getattr(settings, "telegram_webhook_enqueue_timeout_ms", 250)),
    )
    enqueued = await _enqueue_update(
        update_payload=update_payload,
        update_id=update_id,
        timeout_seconds=enqueue_timeout_ms / 1000.0,
    )
    if not enqueued:
        # Reliability invariant: never acknowledge (2xx) a webhook update that we failed to enqueue.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "retry"},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "queued"},
    )
