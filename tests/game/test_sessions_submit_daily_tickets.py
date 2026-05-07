from __future__ import annotations

from tests.game.sessions_submit_daily_support import (
    NOW_UTC,
    UUID,
    SimpleNamespace,
    _Session,
    datetime,
    pytest,
    sessions_submit_daily,
    uuid4,
)


@pytest.mark.asyncio
async def test_credit_daily_duel_ticket_is_idempotent_for_same_daily_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_purchases: list[SimpleNamespace] = []
    credited_purchase_ids: list[UUID] = []
    product = SimpleNamespace(product_code="FRIEND_CHALLENGE_5", stars_amount=5)
    purchase_store: dict[str, SimpleNamespace] = {}
    daily_run_id = uuid4()

    async def _fake_get_by_idempotency_key(_session, idempotency_key: str):
        return purchase_store.get(idempotency_key)

    def _fake_build_purchase(
        built_product,
        *,
        user_id: int,
        idempotency_key: str,
        discount_stars_amount: int,
        applied_promo_code_id,
        now_utc: datetime,
    ):
        del user_id, discount_stars_amount, applied_promo_code_id, now_utc
        purchase = SimpleNamespace(
            id=uuid4(),
            product_code=built_product.product_code,
            idempotency_key=idempotency_key,
            status="CREATED",
        )
        return purchase

    async def _fake_create(_session, *, purchase, created_at: datetime):
        del _session, created_at
        purchase_store[purchase.idempotency_key] = purchase
        created_purchases.append(purchase)
        return purchase

    async def _fake_apply_zero_cost_purchase(_session, *, purchase_id: UUID, user_id: int, now_utc):
        del _session, user_id, now_utc
        credited_purchase_ids.append(purchase_id)
        for purchase in purchase_store.values():
            if purchase.id == purchase_id and purchase.status != "CREDITED":
                purchase.status = "CREDITED"
                return SimpleNamespace(idempotent_replay=False)
        return SimpleNamespace(idempotent_replay=True)

    monkeypatch.setattr(sessions_submit_daily, "get_product", lambda _product_code: product)
    monkeypatch.setattr(
        sessions_submit_daily.PurchasesRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(sessions_submit_daily.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(
        sessions_submit_daily,
        "_get_purchase_service",
        lambda: SimpleNamespace(
            _build_purchase=_fake_build_purchase,
            apply_zero_cost_purchase=_fake_apply_zero_cost_purchase,
        ),
    )

    await sessions_submit_daily._credit_daily_duel_ticket(
        _Session(),
        user_id=11,
        daily_run_id=daily_run_id,
        now_utc=NOW_UTC,
    )
    await sessions_submit_daily._credit_daily_duel_ticket(
        _Session(),
        user_id=11,
        daily_run_id=daily_run_id,
        now_utc=NOW_UTC,
    )

    assert len(created_purchases) == 1
    assert len({purchase.id for purchase in created_purchases}) == 1
    assert len(credited_purchase_ids) == 2
    assert len(set(credited_purchase_ids)) == 1


def test_get_purchase_service_imports_purchase_service_lazily() -> None:
    from app.economy.purchases.service import PurchaseService

    assert sessions_submit_daily._get_purchase_service() is PurchaseService


@pytest.mark.asyncio
async def test_credit_daily_duel_ticket_propagates_purchase_service_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_import_error():
        raise ImportError("purchase service unavailable")

    monkeypatch.setattr(sessions_submit_daily, "_get_purchase_service", _raise_import_error)

    with pytest.raises(ImportError, match="purchase service unavailable"):
        await sessions_submit_daily._credit_daily_duel_ticket(
            _Session(),
            user_id=11,
            daily_run_id=uuid4(),
            now_utc=NOW_UTC,
        )
