from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.workers.tasks import payments_reliability_async
from tests.workers.payments_reliability_async_support import SessionLocalStub


def _patch_payment_invariant_counts(
    monkeypatch: pytest.MonkeyPatch,
    *,
    precheckout_stuck: int = 0,
    paid_uncredited_stuck: int = 0,
    missing_entitlement: int = 0,
    missing_ledger: int = 0,
) -> None:
    async def _precheckout_count(session: object, *, older_than_utc) -> int:
        del session, older_than_utc
        return precheckout_stuck

    async def _paid_uncredited_count(session: object, *, older_than_utc) -> int:
        del session, older_than_utc
        return paid_uncredited_stuck

    async def _missing_entitlement(session: object) -> int:
        del session
        return missing_entitlement

    async def _missing_ledger(session: object) -> int:
        del session
        return missing_ledger

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "count_precheckout_ok_older_than",
        _precheckout_count,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "count_paid_uncredited_older_than",
        _paid_uncredited_count,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "count_credited_premium_without_entitlement",
        _missing_entitlement,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "count_credited_stars_without_purchase_credit",
        _missing_ledger,
    )


def _patch_alert_recorder(
    monkeypatch: pytest.MonkeyPatch,
    alerts: list[dict[str, object]],
) -> None:
    async def _send_alert(*, event: str, payload: dict[str, object]) -> bool:
        alerts.append({"event": event, "payload": payload})
        return True

    monkeypatch.setattr(payments_reliability_async, "send_ops_alert", _send_alert)


@pytest.mark.asyncio
async def test_expire_stale_unpaid_invoices_async_counts_expired_invoices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local_stub = SessionLocalStub()
    logged: list[dict[str, object]] = []

    async def _expired(session: object, *, older_than_utc) -> int:
        del session, older_than_utc
        return 4

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "expire_stale_unpaid_invoices",
        _expired,
    )
    monkeypatch.setattr(
        payments_reliability_async.logger,
        "info",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}),
    )

    result = await payments_reliability_async.expire_stale_unpaid_invoices_async(stale_minutes=30)

    assert result == {"expired_invoices": 4}
    assert logged == [{"event": "stale_unpaid_invoices_expiry_finished", "expired_invoices": 4}]


@pytest.mark.asyncio
async def test_run_payment_invariant_alerts_async_emits_stuck_payment_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts: list[dict[str, object]] = []
    _patch_payment_invariant_counts(
        monkeypatch,
        precheckout_stuck=2,
        paid_uncredited_stuck=1,
    )
    _patch_alert_recorder(monkeypatch, alerts)

    result = await payments_reliability_async.run_payment_invariant_alerts_async()

    assert result["precheckout_stuck"] == 2
    assert result["paid_uncredited_stuck"] == 1
    assert [alert["event"] for alert in alerts] == [
        "payments_precheckout_stuck_detected",
        "payments_paid_uncredited_stuck_detected",
    ]


@pytest.mark.asyncio
async def test_run_payment_invariant_alerts_async_emits_credit_invariant_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts: list[dict[str, object]] = []
    _patch_payment_invariant_counts(
        monkeypatch,
        missing_entitlement=1,
        missing_ledger=2,
    )
    _patch_alert_recorder(monkeypatch, alerts)

    result = await payments_reliability_async.run_payment_invariant_alerts_async()

    assert result["credited_premium_missing_entitlement"] == 1
    assert result["credited_stars_missing_purchase_credit"] == 2
    assert alerts == [
        {
            "event": "payments_credit_invariant_failed",
            "payload": {
                "credit_invariant_failures": 3,
                "credited_premium_missing_entitlement": 1,
                "credited_stars_missing_purchase_credit": 2,
            },
        }
    ]


@pytest.mark.asyncio
async def test_run_payment_invariant_alerts_async_skips_alerts_when_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts: list[dict[str, object]] = []
    _patch_payment_invariant_counts(monkeypatch)
    _patch_alert_recorder(monkeypatch, alerts)

    result = await payments_reliability_async.run_payment_invariant_alerts_async()

    assert result == {
        "precheckout_stuck": 0,
        "paid_uncredited_stuck": 0,
        "credited_premium_missing_entitlement": 0,
        "credited_stars_missing_purchase_credit": 0,
    }
    assert alerts == []


@pytest.mark.asyncio
async def test_run_refund_promo_rollback_async_counts_each_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = uuid4()
    skipped_by_status = uuid4()
    skipped_by_promo = uuid4()
    rolled_back = uuid4()
    not_rolled_back = uuid4()
    session_local_stub = SessionLocalStub()

    async def _get_purchase_ids(session: object, *, limit: int) -> list[UUID]:
        del session, limit
        return [missing, skipped_by_status, skipped_by_promo, rolled_back, not_rolled_back]

    async def _get_purchase(session: object, purchase_id: UUID) -> SimpleNamespace | None:
        del session
        if purchase_id == missing:
            return None
        if purchase_id == skipped_by_status:
            return SimpleNamespace(
                id=skipped_by_status,
                status="CREATED",
                applied_promo_code_id=99,
            )
        if purchase_id == skipped_by_promo:
            return SimpleNamespace(
                id=skipped_by_promo,
                status="REFUNDED",
                applied_promo_code_id=None,
            )
        if purchase_id == not_rolled_back:
            return SimpleNamespace(
                id=not_rolled_back,
                status="REFUNDED",
                applied_promo_code_id=222,
            )
        return SimpleNamespace(
            id=rolled_back,
            status="REFUNDED",
            applied_promo_code_id=111,
        )

    async def _revoke_redemption(
        session: object,
        *,
        purchase_id: UUID,
        promo_code_id: int,
        now_utc,
    ) -> tuple[None, None, bool]:
        del session, now_utc
        assert promo_code_id in (111, 222)
        return None, None, promo_code_id == 111

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "get_refunded_purchase_ids_with_pending_redemption_revoke",
        _get_purchase_ids,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_id_for_update",
        _get_purchase,
    )
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "revoke_redemption_for_refund",
        _revoke_redemption,
    )

    result = await payments_reliability_async.run_refund_promo_rollback_async(batch_size=5)

    assert result == {
        "examined": 5,
        "rolled_back": 1,
        "skipped": 3,
        "missing": 1,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_run_refund_promo_rollback_async_counts_error_when_repo_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    session_local_stub = SessionLocalStub()

    async def _get_purchase_ids(session: object, *, limit: int) -> list[UUID]:
        del session, limit
        return [purchase_id]

    async def _get_purchase(session: object, purchase_id: UUID) -> None:
        del session, purchase_id
        raise RuntimeError("db error")

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "get_refunded_purchase_ids_with_pending_redemption_revoke",
        _get_purchase_ids,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_id_for_update",
        _get_purchase,
    )

    result = await payments_reliability_async.run_refund_promo_rollback_async(batch_size=1)

    assert result == {
        "examined": 1,
        "rolled_back": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 1,
    }


@pytest.mark.asyncio
async def test_run_refund_promo_rollback_async_counts_error_when_revoke_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    session_local_stub = SessionLocalStub()

    async def _get_purchase_ids(session: object, *, limit: int) -> list[UUID]:
        del session, limit
        return [purchase_id]

    async def _get_purchase(session: object, purchase_id: UUID) -> SimpleNamespace:
        del session
        return SimpleNamespace(
            id=purchase_id,
            status="REFUNDED",
            applied_promo_code_id=123,
        )

    async def _revoke_redemption(
        session: object,
        *,
        purchase_id: UUID,
        promo_code_id: int,
        now_utc,
    ) -> tuple[None, None, bool]:
        del session, purchase_id, promo_code_id, now_utc
        raise RuntimeError("broken")

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "get_refunded_purchase_ids_with_pending_redemption_revoke",
        _get_purchase_ids,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_id_for_update",
        _get_purchase,
    )
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "revoke_redemption_for_refund",
        _revoke_redemption,
    )

    result = await payments_reliability_async.run_refund_promo_rollback_async(batch_size=50)

    assert result == {
        "examined": 1,
        "rolled_back": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 1,
    }
