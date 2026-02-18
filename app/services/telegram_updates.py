from __future__ import annotations

import secrets


def extract_update_id(update_payload: object) -> int | None:
    if not isinstance(update_payload, dict):
        return None

    update_id = update_payload.get("update_id")
    if isinstance(update_id, int):
        return update_id
    return None


def is_valid_webhook_secret(*, expected_secret: str, received_secret: str | None) -> bool:
    if not expected_secret or not received_secret:
        return False
    return secrets.compare_digest(expected_secret, received_secret)
