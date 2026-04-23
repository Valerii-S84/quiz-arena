from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers.tasks import payments_reliability_async


class _SessionContextStub:
    def __init__(self, session: object, *, fail_on_commit: bool = False) -> None:
        self._session = session
        self._fail_on_commit = fail_on_commit

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None and self._fail_on_commit:
            raise RuntimeError("commit failed")
        return False


class _SessionLocalStub:
    def __init__(self) -> None:
        self._call_count = 0

    def begin(self) -> _SessionContextStub:
        self._call_count += 1
        return _SessionContextStub(object(), fail_on_commit=self._call_count == 2)


@pytest.mark.asyncio
async def test_run_refund_promo_rollback_async_counts_error_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    session_local_stub = _SessionLocalStub()

    async def _get_purchase_ids(session, *, limit: int) -> list[object]:
        del session, limit
        return [purchase_id]

    async def _get_purchase(session, purchase_id):
        del session, purchase_id
        return SimpleNamespace(
            id=uuid4(),
            status="REFUNDED",
            applied_promo_code_id=123,
        )

    async def _revoke_redemption(session, *, purchase_id, promo_code_id, now_utc):
        del session, purchase_id, promo_code_id, now_utc
        return None, None, True

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
