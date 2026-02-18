from app.services.payments_reliability import (
    compute_product_stars_mismatch_count,
    compute_reconciliation_diff,
    reconciliation_status,
)


def test_compute_reconciliation_diff_includes_stale_paid_uncredited() -> None:
    diff = compute_reconciliation_diff(
        paid_purchases_count=12,
        credited_purchases_count=10,
        stale_paid_uncredited_count=3,
        paid_stars_total=120,
        credited_stars_total=120,
        product_stars_mismatch_count=0,
    )
    assert diff == 5


def test_compute_reconciliation_diff_includes_stars_and_product_mismatches() -> None:
    diff = compute_reconciliation_diff(
        paid_purchases_count=10,
        credited_purchases_count=10,
        stale_paid_uncredited_count=0,
        paid_stars_total=100,
        credited_stars_total=99,
        product_stars_mismatch_count=2,
    )
    assert diff == 3


def test_compute_reconciliation_diff_clamps_negative_stale_count() -> None:
    diff = compute_reconciliation_diff(
        paid_purchases_count=10,
        credited_purchases_count=10,
        stale_paid_uncredited_count=-1,
        paid_stars_total=100,
        credited_stars_total=100,
        product_stars_mismatch_count=0,
    )
    assert diff == 0


def test_compute_product_stars_mismatch_count() -> None:
    mismatch_count = compute_product_stars_mismatch_count(
        paid_stars_by_product={"ENERGY_10": 100, "MEGA_PACK_15": 30},
        credited_stars_by_product={"ENERGY_10": 100, "PREMIUM_MONTH": 99},
    )
    assert mismatch_count == 2


def test_reconciliation_status() -> None:
    assert reconciliation_status(0) == "OK"
    assert reconciliation_status(1) == "DIFF"
