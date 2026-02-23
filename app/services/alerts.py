from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from app.core.config import get_settings
from app.services.alerts_config import DEFAULT_PAGERDUTY_EVENTS_URL, AlertRoute, AlertTarget
from app.services.alerts_delivery import post_json
from app.services.alerts_payloads import build_channel_payload
from app.services.alerts_routes import resolve_alert_route, resolve_targets

logger = structlog.get_logger(__name__)


async def send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
    settings = get_settings()
    route = resolve_alert_route(
        event=event,
        policy_raw=_setting_str(settings, "ops_alert_escalation_policy_json"),
    )
    targets = resolve_targets(route=route, settings=settings)
    if not targets:
        return False

    sent_at = datetime.now(timezone.utc)
    app_env = _setting_str(settings, "app_env") or "dev"
    pagerduty_routing_key = _setting_str(settings, "ops_alert_pagerduty_routing_key")

    delivered_to: list[str] = []
    failed_to: list[str] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for target in targets:
            body = build_channel_payload(
                channel=target.channel,
                event=event,
                payload=payload,
                sent_at=sent_at,
                route=route,
                app_env=app_env,
                pagerduty_routing_key=pagerduty_routing_key,
            )
            delivered = await post_json(
                client=client,
                url=target.url,
                body=body,
                event=event,
                channel=target.channel,
            )
            if delivered:
                delivered_to.append(target.channel)
            else:
                failed_to.append(target.channel)

    if not delivered_to:
        logger.error(
            "ops_alert_delivery_exhausted",
            alert_event=event,
            severity=route.severity,
            escalation_tier=route.escalation_tier,
            failed_to=failed_to,
        )
        return False

    logger.info(
        "ops_alert_delivered",
        alert_event=event,
        severity=route.severity,
        escalation_tier=route.escalation_tier,
        delivered_to=delivered_to,
        failed_to=failed_to,
    )
    return True


def _setting_str(settings: object, attr: str) -> str:
    value = getattr(settings, attr, "")
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "AlertRoute",
    "AlertTarget",
    "DEFAULT_PAGERDUTY_EVENTS_URL",
    "send_ops_alert",
]
