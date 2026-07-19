from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.economy.purchases.errors import (
    PurchaseNotFoundError,
    PurchaseRefundInvariantError,
    PurchaseRefundValidationError,
)
from app.economy.purchases.service import refund as purchase_refund
from tests.purchase_service_test_helpers import NOW, SessionStub, refund_purchase_state


@pytest.mark.asyncio
async def test_refund_purchase_rejects_missing_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return None

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    with pytest.raises(PurchaseNotFoundError):
        await purchase_refund.refund_purchase(
            SessionStub(),
            purchase_id=uuid4(),
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_refund_purchase_rejects_non_refundable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="CREATED")

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await purchase_refund.refund_purchase(
            SessionStub(),
            purchase_id=purchase.id,
            now_utc=NOW,
        )

    assert purchase.status == "CREATED"


@pytest.mark.asyncio
async def test_refund_purchase_rejects_credit_pending_review_without_provider_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="FAILED_CREDIT_PENDING_REVIEW")

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fail_get_purchase_credit_for_update(*_args, **_kwargs):
        pytest.fail("generic review-pending refund must not inspect credit evidence")

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.LedgerRepo,
        "get_purchase_credit_for_update",
        _fail_get_purchase_credit_for_update,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await purchase_refund.refund_purchase(
            SessionStub(),
            purchase_id=purchase.id,
            now_utc=NOW,
        )

    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
    assert purchase.refunded_at is None


@pytest.mark.asyncio
async def test_refund_purchase_rejects_missing_credit_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="CREDITED")

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        return None

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.LedgerRepo,
        "get_purchase_credit_for_update",
        _fake_get_purchase_credit_for_update,
    )

    with pytest.raises(PurchaseRefundInvariantError):
        await purchase_refund.refund_purchase(
            SessionStub(),
            purchase_id=purchase.id,
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_refund_purchase_wraps_credit_lookup_invariant_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="CREDITED")

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        raise ValueError("multiple purchase credit ledger entries found")

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.LedgerRepo,
        "get_purchase_credit_for_update",
        _fake_get_purchase_credit_for_update,
    )

    with pytest.raises(PurchaseRefundInvariantError):
        await purchase_refund.refund_purchase(
            SessionStub(),
            purchase_id=purchase.id,
            now_utc=NOW,
        )

    assert purchase.status == "CREDITED"
