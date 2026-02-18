from app.services.payments_reliability import compute_reconciliation_diff, reconciliation_status


def test_compute_reconciliation_diff_includes_stale_paid_uncredited() -> None:
    diff = compute_reconciliation_diff(
        paid_purchases_count=12,
        credited_purchases_count=10,
        stale_paid_uncredited_count=3,
    )
    assert diff == 5


def test_compute_reconciliation_diff_clamps_negative_stale_count() -> None:
    diff = compute_reconciliation_diff(
        paid_purchases_count=10,
        credited_purchases_count=10,
        stale_paid_uncredited_count=-1,
    )
    assert diff == 0


def test_reconciliation_status() -> None:
    assert reconciliation_status(0) == "OK"
    assert reconciliation_status(1) == "DIFF"
