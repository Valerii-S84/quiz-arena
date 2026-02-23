from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger("app.services.alerts")


async def post_json(
    *,
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    event: str,
    channel: str,
) -> bool:
    try:
        response = await client.post(url, json=body)
        response.raise_for_status()
        return True
    except Exception:
        logger.exception(
            "ops_alert_delivery_failed",
            alert_event=event,
            provider=channel,
        )
        return False
