from __future__ import annotations

SAFE_SUCCESSFUL_PAYMENT_KEYS = frozenset(
    {
        "_credit_recovery_failures",
        "currency",
        "recovered_by",
        "source",
        "total_amount",
        "transaction_date",
        "utm",
    }
)


def sanitize_successful_payment_payload(
    raw_successful_payment: dict[str, object],
) -> dict[str, object]:
    sanitized = {
        key: value
        for key, value in raw_successful_payment.items()
        if key in SAFE_SUCCESSFUL_PAYMENT_KEYS
    }
    sanitized["raw_payload_stored"] = False
    return sanitized


def successful_payment_validation_error(
    *,
    purchase,
    invoice_payload: str,
    telegram_payment_charge_id: str | None,
    raw_successful_payment: dict[str, object],
) -> str | None:
    if purchase.stars_amount == 0:
        return None

    if invoice_payload != purchase.invoice_payload:
        return "invoice_payload_mismatch"
    raw_invoice_payload = raw_successful_payment.get("invoice_payload")
    if raw_invoice_payload is not None:
        if not isinstance(raw_invoice_payload, str) or not raw_invoice_payload:
            return "invalid_invoice_payload"
        if raw_invoice_payload != invoice_payload:
            return "invoice_payload_mismatch"

    if not isinstance(telegram_payment_charge_id, str) or not telegram_payment_charge_id:
        return "missing_telegram_payment_charge_id"

    expected_currency = getattr(purchase, "currency", "XTR") or "XTR"
    if raw_successful_payment.get("currency") != expected_currency:
        return "currency_mismatch"

    total_amount = raw_successful_payment.get("total_amount")
    if total_amount is None:
        return "missing_total_amount"
    if type(total_amount) is not int:
        return "invalid_total_amount"
    if total_amount != purchase.stars_amount:
        return "total_amount_mismatch"
    return None
