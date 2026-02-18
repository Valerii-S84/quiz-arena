from __future__ import annotations


def compute_reconciliation_diff(
    *,
    paid_purchases_count: int,
    credited_purchases_count: int,
    stale_paid_uncredited_count: int,
) -> int:
    return abs(paid_purchases_count - credited_purchases_count) + max(0, stale_paid_uncredited_count)


def reconciliation_status(diff_count: int) -> str:
    return "OK" if diff_count == 0 else "DIFF"
