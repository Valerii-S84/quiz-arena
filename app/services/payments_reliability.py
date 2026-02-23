from __future__ import annotations


def compute_reconciliation_diff(
    *,
    paid_purchases_count: int,
    credited_purchases_count: int,
    stale_paid_uncredited_count: int,
    paid_stars_total: int,
    credited_stars_total: int,
    product_stars_mismatch_count: int,
) -> int:
    return (
        abs(paid_purchases_count - credited_purchases_count)
        + max(0, stale_paid_uncredited_count)
        + (1 if paid_stars_total != credited_stars_total else 0)
        + max(0, product_stars_mismatch_count)
    )


def compute_product_stars_mismatch_count(
    *,
    paid_stars_by_product: dict[str, int],
    credited_stars_by_product: dict[str, int],
) -> int:
    product_codes = set(paid_stars_by_product) | set(credited_stars_by_product)
    return sum(
        1
        for product_code in product_codes
        if paid_stars_by_product.get(product_code, 0)
        != credited_stars_by_product.get(product_code, 0)
    )


def reconciliation_status(diff_count: int) -> str:
    return "OK" if diff_count == 0 else "DIFF"
