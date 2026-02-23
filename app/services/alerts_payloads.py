from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.services.alerts_config import SEVERITY_COLOR, AlertRoute


def _payload_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def build_generic_payload(
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


def build_slack_payload(
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
                    {
                        "title": "Payload",
                        "value": _payload_text(payload),
                        "short": False,
                    },
                ],
            }
        ],
    }


def build_pagerduty_payload(
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


def build_channel_payload(
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
        return build_generic_payload(event=event, payload=payload, sent_at=sent_at, route=route)
    if channel == "slack":
        return build_slack_payload(
            event=event,
            payload=payload,
            sent_at=sent_at,
            route=route,
            app_env=app_env,
        )
    if channel == "pagerduty":
        return build_pagerduty_payload(
            event=event,
            payload=payload,
            sent_at=sent_at,
            route=route,
            app_env=app_env,
            routing_key=pagerduty_routing_key,
        )
    raise ValueError(f"Unsupported alert channel: {channel}")
