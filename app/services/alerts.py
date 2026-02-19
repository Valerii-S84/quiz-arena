from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)
DEFAULT_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"
VALID_CHANNELS = {"generic", "slack", "pagerduty"}
VALID_SEVERITIES = {"critical", "error", "warning", "info"}
SEVERITY_COLOR = {
    "critical": "#B42318",
    "error": "#F04438",
    "warning": "#F79009",
    "info": "#1570EF",
}


@dataclass(frozen=True)
class AlertRoute:
    channels: tuple[str, ...]
    severity: str
    escalation_tier: str


@dataclass(frozen=True)
class AlertTarget:
    channel: str
    url: str


DEFAULT_ALERT_ROUTE = AlertRoute(
    channels=("generic",),
    severity="warning",
    escalation_tier="ops_l3",
)
EVENT_ALERT_ROUTES = {
    "promo_campaign_auto_paused": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
    "payments_reconciliation_diff_detected": AlertRoute(
        channels=("pagerduty", "slack", "generic"),
        severity="critical",
        escalation_tier="ops_l1",
    ),
    "payments_recovery_review_required": AlertRoute(
        channels=("pagerduty", "slack", "generic"),
        severity="error",
        escalation_tier="ops_l1",
    ),
    "offers_conversion_drop_detected": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
    "offers_spam_anomaly_detected": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
    "referral_fraud_spike_detected": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
}


def _setting_str(settings: object, attr: str) -> str:
    value = getattr(settings, attr, "")
    return value.strip() if isinstance(value, str) else ""


def _normalize_channels(raw_channels: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(raw_channels, list):
        return fallback

    ordered: list[str] = []
    for channel in raw_channels:
        if not isinstance(channel, str):
            continue
        channel_name = channel.strip().lower()
        if channel_name not in VALID_CHANNELS or channel_name in ordered:
            continue
        ordered.append(channel_name)

    return tuple(ordered) if ordered else fallback


def _normalize_severity(raw_severity: object, fallback: str) -> str:
    if not isinstance(raw_severity, str):
        return fallback
    severity = raw_severity.strip().lower()
    return severity if severity in VALID_SEVERITIES else fallback


def _normalize_escalation_tier(raw_tier: object, fallback: str) -> str:
    if not isinstance(raw_tier, str):
        return fallback
    tier = raw_tier.strip()
    return tier if tier else fallback


def _parse_policy_overrides(raw_policy: str) -> dict[str, dict[str, object]]:
    if not raw_policy:
        return {}

    try:
        parsed = json.loads(raw_policy)
    except json.JSONDecodeError:
        logger.warning("ops_alert_policy_parse_failed")
        return {}

    if not isinstance(parsed, dict):
        logger.warning("ops_alert_policy_invalid_shape")
        return {}

    normalized: dict[str, dict[str, object]] = {}
    for event_name, route in parsed.items():
        if not isinstance(event_name, str) or not isinstance(route, dict):
            continue
        normalized[event_name] = route

    return normalized


def _resolve_alert_route(*, event: str, policy_raw: str) -> AlertRoute:
    base_route = EVENT_ALERT_ROUTES.get(event, DEFAULT_ALERT_ROUTE)
    overrides = _parse_policy_overrides(policy_raw)
    override = overrides.get(event) or overrides.get("*")
    if override is None:
        return base_route

    channels = _normalize_channels(override.get("channels"), base_route.channels)
    severity = _normalize_severity(override.get("severity"), base_route.severity)
    escalation_tier = _normalize_escalation_tier(
        override.get("escalation_tier"),
        base_route.escalation_tier,
    )
    return AlertRoute(
        channels=channels,
        severity=severity,
        escalation_tier=escalation_tier,
    )


def _resolve_targets(*, route: AlertRoute, settings: object) -> list[AlertTarget]:
    generic_webhook_url = _setting_str(settings, "ops_alert_webhook_url")
    slack_webhook_url = _setting_str(settings, "ops_alert_slack_webhook_url")
    pagerduty_routing_key = _setting_str(settings, "ops_alert_pagerduty_routing_key")
    pagerduty_events_url = _setting_str(settings, "ops_alert_pagerduty_events_url")
    if not pagerduty_events_url:
        pagerduty_events_url = DEFAULT_PAGERDUTY_EVENTS_URL

    channel_to_url: dict[str, str] = {
        "generic": generic_webhook_url,
        "slack": slack_webhook_url,
    }
    if pagerduty_routing_key:
        channel_to_url["pagerduty"] = pagerduty_events_url

    targets: list[AlertTarget] = []
    for channel in route.channels:
        url = channel_to_url.get(channel, "")
        if url:
            targets.append(AlertTarget(channel=channel, url=url))

    if not targets and generic_webhook_url:
        targets.append(AlertTarget(channel="generic", url=generic_webhook_url))

    return targets


def _payload_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _build_generic_payload(
    *,
    event: str,
    payload: dict[str, object],
    sent_at: datetime,
    route: AlertRoute,
) -> dict[str, object]:
    return {
        "event": event,
        "payload": payload,
        "sent_at": sent_at.isoformat(),
        "severity": route.severity,
        "escalation_tier": route.escalation_tier,
    }


def _build_slack_payload(
    *,
    event: str,
    payload: dict[str, object],
    sent_at: datetime,
    route: AlertRoute,
    app_env: str,
) -> dict[str, object]:
    return {
        "text": f"[{route.severity.upper()}][{route.escalation_tier}] {event}",
        "attachments": [
            {
                "color": SEVERITY_COLOR.get(route.severity, SEVERITY_COLOR["warning"]),
                "fields": [
                    {"title": "Environment", "value": app_env, "short": True},
                    {"title": "Sent At", "value": sent_at.isoformat(), "short": True},
                    {"title": "Event", "value": event, "short": False},
                    {"title": "Payload", "value": _payload_text(payload), "short": False},
                ],
            }
        ],
    }


def _build_pagerduty_payload(
    *,
    event: str,
    payload: dict[str, object],
    sent_at: datetime,
    route: AlertRoute,
    app_env: str,
    routing_key: str,
) -> dict[str, object]:
    return {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": f"{event}:{route.escalation_tier}",
        "payload": {
            "summary": f"[{app_env}] {event}",
            "source": f"quiz-arena-bot/{app_env}",
            "severity": route.severity,
            "timestamp": sent_at.isoformat(),
            "component": "quiz-arena-backend",
            "group": route.escalation_tier,
            "custom_details": {
                "event": event,
                "payload": payload,
                "escalation_tier": route.escalation_tier,
            },
        },
    }


def _build_channel_payload(
    *,
    channel: str,
    event: str,
    payload: dict[str, object],
    sent_at: datetime,
    route: AlertRoute,
    app_env: str,
    pagerduty_routing_key: str,
) -> dict[str, Any]:
    if channel == "generic":
        return _build_generic_payload(event=event, payload=payload, sent_at=sent_at, route=route)
    if channel == "slack":
        return _build_slack_payload(
            event=event,
            payload=payload,
            sent_at=sent_at,
            route=route,
            app_env=app_env,
        )
    if channel == "pagerduty":
        return _build_pagerduty_payload(
            event=event,
            payload=payload,
            sent_at=sent_at,
            route=route,
            app_env=app_env,
            routing_key=pagerduty_routing_key,
        )
    raise ValueError(f"Unsupported alert channel: {channel}")


async def _post_json(
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


async def send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
    settings = get_settings()
    route = _resolve_alert_route(
        event=event,
        policy_raw=_setting_str(settings, "ops_alert_escalation_policy_json"),
    )
    targets = _resolve_targets(route=route, settings=settings)
    if not targets:
        return False

    sent_at = datetime.now(timezone.utc)
    app_env = _setting_str(settings, "app_env") or "dev"
    pagerduty_routing_key = _setting_str(settings, "ops_alert_pagerduty_routing_key")

    delivered_to: list[str] = []
    failed_to: list[str] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for target in targets:
            body = _build_channel_payload(
                channel=target.channel,
                event=event,
                payload=payload,
                sent_at=sent_at,
                route=route,
                app_env=app_env,
                pagerduty_routing_key=pagerduty_routing_key,
            )
            delivered = await _post_json(
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
