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
