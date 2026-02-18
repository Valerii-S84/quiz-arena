from app.economy.purchases.recovery import (
    MAX_CREDIT_RECOVERY_ATTEMPTS,
    RECOVERY_FAILURES_KEY,
    increment_recovery_failures,
)


def test_increment_recovery_failures_initializes_counter() -> None:
    payload, failures = increment_recovery_failures(None)
    assert failures == 1
    assert payload[RECOVERY_FAILURES_KEY] == 1


def test_increment_recovery_failures_increments_existing_counter() -> None:
    payload, failures = increment_recovery_failures(
        {
            "currency": "XTR",
            RECOVERY_FAILURES_KEY: MAX_CREDIT_RECOVERY_ATTEMPTS - 1,
        }
    )
    assert failures == MAX_CREDIT_RECOVERY_ATTEMPTS
    assert payload[RECOVERY_FAILURES_KEY] == MAX_CREDIT_RECOVERY_ATTEMPTS


def test_increment_recovery_failures_handles_invalid_counter_value() -> None:
    payload, failures = increment_recovery_failures({RECOVERY_FAILURES_KEY: "bad"})
    assert failures == 1
    assert payload[RECOVERY_FAILURES_KEY] == 1
