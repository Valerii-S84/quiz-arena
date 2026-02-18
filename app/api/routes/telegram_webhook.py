from __future__ import annotations

import structlog
from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.services.telegram_updates import extract_update_id, is_valid_webhook_secret
from app.workers.tasks.telegram_updates import process_telegram_update

router = APIRouter(tags=["telegram"])
logger = structlog.get_logger(__name__)


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request) -> dict[str, str]:
    settings = get_settings()
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not is_valid_webhook_secret(
        expected_secret=settings.telegram_webhook_secret,
        received_secret=received_secret,
    ):
        logger.warning("telegram_webhook_invalid_secret")
        return {"status": "ignored"}

    try:
        update_payload = await request.json()
    except Exception:
        logger.warning("telegram_webhook_invalid_json")
        return {"status": "ignored"}

    update_id = extract_update_id(update_payload)
    if update_id is None:
        logger.warning("telegram_webhook_missing_update_id")
        return {"status": "ignored"}

    process_telegram_update.delay(update_payload=update_payload, update_id=update_id)
    return {"status": "queued"}
