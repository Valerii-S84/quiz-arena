from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


async def send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
    webhook_url = get_settings().ops_alert_webhook_url.strip()
    if not webhook_url:
        return False

    body = {
        "event": event,
        "payload": payload,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(webhook_url, json=body)
            response.raise_for_status()
    except Exception:
        logger.exception("ops_alert_delivery_failed", alert_event=event)
        return False

    logger.info("ops_alert_delivered", alert_event=event)
    return True
