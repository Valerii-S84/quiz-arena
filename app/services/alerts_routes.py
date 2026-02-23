from __future__ import annotations

import json

import structlog

from app.services.alerts_config import (
    DEFAULT_ALERT_ROUTE,
    DEFAULT_PAGERDUTY_EVENTS_URL,
    EVENT_ALERT_ROUTES,
    VALID_CHANNELS,
    VALID_SEVERITIES,
    AlertRoute,
    AlertTarget,
)

logger = structlog.get_logger("app.services.alerts")


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


def resolve_alert_route(*, event: str, policy_raw: str) -> AlertRoute:
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


def resolve_targets(*, route: AlertRoute, settings: object) -> list[AlertTarget]:
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
