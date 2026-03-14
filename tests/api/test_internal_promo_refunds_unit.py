from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

import app.api.routes.internal_promo_refunds as internal_promo_refunds
from app.api.routes.internal_promo_models import PromoRefundRollbackRequest
from app.economy.purchases.errors import (
    PurchaseNotFoundError,
    PurchaseRefundInvariantError,
    PurchaseRefundValidationError,
)


class _DummySessionBegin:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _DummySessionLocal:
    def __init__(self, session: object) -> None:
        self._session = session

    def begin(self) -> _DummySessionBegin:
        return _DummySessionBegin(self._session)


def _payload(purchase_id: UUID | None = None) -> PromoRefundRollbackRequest:
    return PromoRefundRollbackRequest(
        purchase_id=purchase_id or uuid4(),
        reason="manual rollback",
    )


@pytest.mark.asyncio
async def test_rollback_promo_for_refund_maps_purchase_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    monkeypatch.setattr(internal_promo_refunds, "_assert_internal_access", lambda _request: None)
    monkeypatch.setattr(internal_promo_refunds, "SessionLocal", _DummySessionLocal(session))

    async def _fake_refund_purchase(_session, *, purchase_id: UUID, now_utc) -> None:
        assert _session is session
        assert purchase_id
        raise PurchaseNotFoundError

    monkeypatch.setattr(
        internal_promo_refunds.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(HTTPException) as exc_info:
        await internal_promo_refunds.rollback_promo_for_refund(
            payload=_payload(),
            request=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {"code": "E_PURCHASE_NOT_FOUND"}


@pytest.mark.asyncio
async def test_rollback_promo_for_refund_maps_refund_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    monkeypatch.setattr(internal_promo_refunds, "_assert_internal_access", lambda _request: None)
    monkeypatch.setattr(internal_promo_refunds, "SessionLocal", _DummySessionLocal(session))

    async def _fake_refund_purchase(_session, *, purchase_id: UUID, now_utc) -> None:
        raise PurchaseRefundValidationError

    monkeypatch.setattr(
        internal_promo_refunds.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(HTTPException) as exc_info:
        await internal_promo_refunds.rollback_promo_for_refund(
            payload=_payload(),
            request=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "E_PURCHASE_REFUND_NOT_ALLOWED"}


@pytest.mark.asyncio
async def test_rollback_promo_for_refund_maps_refund_invariant_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    monkeypatch.setattr(internal_promo_refunds, "_assert_internal_access", lambda _request: None)
    monkeypatch.setattr(internal_promo_refunds, "SessionLocal", _DummySessionLocal(session))

    async def _fake_refund_purchase(_session, *, purchase_id: UUID, now_utc) -> None:
        raise PurchaseRefundInvariantError

    monkeypatch.setattr(
        internal_promo_refunds.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(HTTPException) as exc_info:
        await internal_promo_refunds.rollback_promo_for_refund(
            payload=_payload(),
            request=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "E_PURCHASE_REFUND_INVARIANT"}


@pytest.mark.asyncio
async def test_rollback_promo_for_refund_returns_idempotent_replay_without_promo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    purchase_id = uuid4()
    purchase = SimpleNamespace(
        id=purchase_id,
        status="REFUNDED",
        applied_promo_code_id=None,
    )
    logged: list[dict[str, object]] = []

    monkeypatch.setattr(internal_promo_refunds, "_assert_internal_access", lambda _request: None)
    monkeypatch.setattr(internal_promo_refunds, "SessionLocal", _DummySessionLocal(session))

    async def _fake_refund_purchase(_session, *, purchase_id: UUID, now_utc):
        return SimpleNamespace(idempotent_replay=True)

    async def _fake_get_by_id_for_update(_session, purchase_id: UUID):
        return purchase

    monkeypatch.setattr(
        internal_promo_refunds.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )
    monkeypatch.setattr(
        internal_promo_refunds.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        internal_promo_refunds.logger,
        "info",
        lambda event, **payload: logged.append({"event": event, **payload}),
    )

    response = await internal_promo_refunds.rollback_promo_for_refund(
        payload=_payload(purchase_id),
        request=SimpleNamespace(),
    )

    assert response.purchase_id == purchase_id
    assert response.purchase_status == "REFUNDED"
    assert response.promo_redemption_id is None
    assert response.promo_code_used_total is None
    assert response.idempotent_replay is True
    assert logged[0]["event"] == "internal_promo_refund_rollback_applied"


@pytest.mark.asyncio
async def test_rollback_promo_for_refund_returns_rollback_metadata_for_promo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    purchase_id = uuid4()
    redemption_id = uuid4()
    purchase = SimpleNamespace(
        id=purchase_id,
        status="REFUNDED",
        applied_promo_code_id=91,
    )

    monkeypatch.setattr(internal_promo_refunds, "_assert_internal_access", lambda _request: None)
    monkeypatch.setattr(internal_promo_refunds, "SessionLocal", _DummySessionLocal(session))

    async def _fake_refund_purchase(_session, *, purchase_id: UUID, now_utc):
        return SimpleNamespace(idempotent_replay=True)

    async def _fake_get_by_id_for_update(_session, purchase_id: UUID):
        return purchase

    async def _fake_revoke_redemption_for_refund(
        _session,
        *,
        purchase_id: UUID,
        promo_code_id: int,
        now_utc,
    ):
        assert purchase_id == purchase.id
        assert promo_code_id == 91
        return (
            SimpleNamespace(id=redemption_id, status="REVOKED"),
            SimpleNamespace(used_total=4),
            True,
        )

    monkeypatch.setattr(
        internal_promo_refunds.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )
    monkeypatch.setattr(
        internal_promo_refunds.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        internal_promo_refunds.PromoRepo,
        "revoke_redemption_for_refund",
        _fake_revoke_redemption_for_refund,
    )

    response = await internal_promo_refunds.rollback_promo_for_refund(
        payload=_payload(purchase_id),
        request=SimpleNamespace(),
    )

    assert response.purchase_id == purchase_id
    assert response.promo_redemption_id == redemption_id
    assert response.promo_redemption_status == "REVOKED"
    assert response.promo_code_id == 91
    assert response.promo_code_used_total == 4
    assert response.idempotent_replay is False
