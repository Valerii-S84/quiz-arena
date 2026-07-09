from app.workers.tasks import payments_reliability


def test_recover_paid_uncredited_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int, stale_minutes: int) -> dict[str, int]:
        return {
            "examined": batch_size,
            "credited": stale_minutes,
            "review": 0,
            "retryable_failure": 0,
            "skipped": 0,
            "missing": 0,
            "errors": 0,
        }

    monkeypatch.setattr(payments_reliability, "recover_paid_uncredited_async", fake_async)

    result = payments_reliability.recover_paid_uncredited(batch_size=7, stale_minutes=5)
    assert result["examined"] == 7
    assert result["credited"] == 5


def test_expire_stale_unpaid_invoices_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, stale_minutes: int) -> dict[str, int]:
        return {"expired_invoices": stale_minutes}

    monkeypatch.setattr(payments_reliability, "expire_stale_unpaid_invoices_async", fake_async)

    result = payments_reliability.expire_stale_unpaid_invoices(stale_minutes=45)
    assert result["expired_invoices"] == 45


def test_run_payment_invariant_alerts_task_wrapper(monkeypatch) -> None:
    async def fake_async(
        *,
        precheckout_stale_minutes: int,
        paid_uncredited_stale_seconds: int,
    ) -> dict[str, int]:
        return {
            "precheckout_stuck": precheckout_stale_minutes,
            "paid_uncredited_stuck": paid_uncredited_stale_seconds,
            "credited_premium_missing_entitlement": 0,
            "credited_stars_missing_purchase_credit": 0,
        }

    monkeypatch.setattr(payments_reliability, "run_payment_invariant_alerts_async", fake_async)

    result = payments_reliability.run_payment_invariant_alerts(
        precheckout_stale_minutes=3,
        paid_uncredited_stale_seconds=60,
    )
    assert result["precheckout_stuck"] == 3
    assert result["paid_uncredited_stuck"] == 60


def test_run_refund_promo_rollback_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, int]:
        return {
            "examined": batch_size,
            "rolled_back": 2,
            "skipped": 0,
            "missing": 0,
            "errors": 0,
        }

    monkeypatch.setattr(payments_reliability, "run_refund_promo_rollback_async", fake_async)

    result = payments_reliability.run_refund_promo_rollback(batch_size=11)
    assert result["examined"] == 11
    assert result["rolled_back"] == 2


def test_run_payments_reconciliation_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, stale_minutes: int) -> dict[str, int | str]:
        return {
            "paid_purchases_count": stale_minutes,
            "credited_purchases_count": 0,
            "stale_paid_uncredited_count": 0,
            "diff_count": 0,
            "status": "OK",
        }

    monkeypatch.setattr(payments_reliability, "run_payments_reconciliation_async", fake_async)

    result = payments_reliability.run_payments_reconciliation(stale_minutes=30)
    assert result["paid_purchases_count"] == 30
    assert result["status"] == "OK"


def test_run_telegram_stars_reconciliation_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, object]:
        return {"status": "disabled", "transactions_examined": 0}

    monkeypatch.setattr(
        payments_reliability,
        "run_telegram_stars_reconciliation_async",
        fake_async,
    )

    result = payments_reliability.run_telegram_stars_reconciliation()
    assert result == {"status": "disabled", "transactions_examined": 0}
