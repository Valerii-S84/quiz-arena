from __future__ import annotations

from copy import deepcopy

RECOVERY_FAILURES_KEY = "_credit_recovery_failures"
MAX_CREDIT_RECOVERY_ATTEMPTS = 3


def increment_recovery_failures(
    raw_successful_payment: dict[str, object] | None,
) -> tuple[dict[str, object], int]:
    payload = deepcopy(raw_successful_payment) if isinstance(raw_successful_payment, dict) else {}
    current_value = payload.get(RECOVERY_FAILURES_KEY, 0)

    try:
        current_failures = int(current_value)
    except (TypeError, ValueError):
        current_failures = 0

    next_failures = current_failures + 1
    payload[RECOVERY_FAILURES_KEY] = next_failures
    return payload, next_failures
