from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.db.models.purchases import Purchase
from app.db.repo.purchases_repo import PurchasesRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _purchase() -> Purchase:
    return Purchase(
        id=uuid4(),
        user_id=7,
        product_code="PREMIUM_30",
        product_type="PREMIUM",
        base_stars_amount=100,
        discount_stars_amount=0,
        stars_amount=100,
        status="CREATED",
        idempotency_key="purchase:idempotency",
        invoice_payload="invoice-payload",
        created_at=datetime(2026, 3, 14, tzinfo=UTC),
    )


async def test_purchase_id_lookups_use_session_get_and_lock_query() -> None:
    purchase = _purchase()
    get_session = RecordingSession(get_result=purchase)

    assert await PurchasesRepo.get_by_id(get_session, purchase.id) is purchase
    assert get_session.get_calls == [(Purchase, purchase.id)]

    lock_session = RecordingSession(_ScalarResult(None))
    assert await PurchasesRepo.get_by_id_for_update(lock_session, purchase.id) is None
    assert lock_session.statement is not None
    lock_sql = compile_statement(lock_session.statement)
    assert str(purchase.id) in lock_sql
    assert "FOR UPDATE" in lock_sql


async def test_purchase_lookup_queries_filter_invoice_idempotency_and_active_status() -> None:
    idempotency_session = RecordingSession(_ScalarResult(None))
    await PurchasesRepo.get_by_idempotency_key(idempotency_session, "purchase:key")
    assert "purchases.idempotency_key = 'purchase:key'" in compile_statement(
        idempotency_session.statement
    )

    invoice_session = RecordingSession(_ScalarResult(None))
    await PurchasesRepo.get_by_invoice_payload(invoice_session, "invoice-1")
    assert "purchases.invoice_payload = 'invoice-1'" in compile_statement(invoice_session.statement)

    invoice_lock_session = RecordingSession(_ScalarResult(None))
    await PurchasesRepo.get_by_invoice_payload_for_update(invoice_lock_session, "invoice-2")
    assert "FOR UPDATE" in compile_statement(invoice_lock_session.statement)

    active_session = RecordingSession(_ScalarResult(None))
    await PurchasesRepo.get_active_invoice_for_user_product(
        active_session,
        user_id=7,
        product_code="PREMIUM_30",
    )
    active_sql = compile_statement(active_session.statement)
    assert "purchases.user_id = 7" in active_sql
    assert "purchases.product_code = 'PREMIUM_30'" in active_sql
    assert "purchases.status IN ('CREATED', 'INVOICE_SENT', 'PRECHECKOUT_OK')" in active_sql
    assert "ORDER BY purchases.created_at DESC" in active_sql
    assert "LIMIT 1" in active_sql

    active_lock_session = RecordingSession(_ScalarResult(None))
    await PurchasesRepo.get_active_invoice_for_user_product_for_update(
        active_lock_session,
        user_id=7,
        product_code="PREMIUM_30",
    )
    assert "FOR UPDATE" in compile_statement(active_lock_session.statement)


async def test_paid_listing_credit_lock_and_stale_expiration_queries() -> None:
    purchase = _purchase()
    older_than = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    credit_session = RecordingSession(_ScalarResult(None))
    assert await PurchasesRepo.get_for_credit_lock(credit_session, purchase.id) is None
    assert "FOR UPDATE" in compile_statement(credit_session.statement)

    list_session = RecordingSession(_ScalarsResult([purchase]))
    rows = await PurchasesRepo.get_paid_uncredited_older_than(
        list_session,
        older_than_utc=older_than,
        limit=25,
    )
    assert rows == [purchase]
    list_sql = compile_statement(list_session.statement)
    assert "purchases.status = 'PAID_UNCREDITED'" in list_sql
    assert "purchases.paid_at IS NOT NULL" in list_sql
    assert "ORDER BY purchases.paid_at ASC" in list_sql
    assert "LIMIT 25" in list_sql

    expire_session = RecordingSession(SimpleNamespace(rowcount=3))
    assert (
        await PurchasesRepo.expire_stale_unpaid_invoices(
            expire_session,
            older_than_utc=older_than,
        )
        == 3
    )
    expire_sql = compile_statement(expire_session.statement)
    assert "UPDATE purchases SET status='FAILED'" in expire_sql
    assert "purchases.status IN ('CREATED', 'INVOICE_SENT')" in expire_sql
    assert "purchases.paid_at IS NULL" in expire_sql


async def test_purchase_count_and_metric_queries_apply_paid_filters() -> None:
    since_utc = datetime(2026, 3, 1, tzinfo=UTC)
    count_session = RecordingSession(_ScalarResult(4))
    assert await PurchasesRepo.count_by_user(count_session, user_id=7) == 4
    assert "purchases.user_id = 7" in compile_statement(count_session.statement)

    paid_user_session = RecordingSession(_ScalarResult(2))
    assert await PurchasesRepo.count_paid_purchases_for_user(paid_user_session, user_id=7) == 2
    paid_user_sql = compile_statement(paid_user_session.statement)
    assert "purchases.paid_at IS NOT NULL" in paid_user_sql
    assert "purchases.stars_amount > 0" in paid_user_sql

    product_session = RecordingSession(_ScalarResult(1))
    assert (
        await PurchasesRepo.count_paid_product_since(
            product_session,
            user_id=7,
            product_code="PREMIUM_30",
            since_utc=since_utc,
        )
        == 1
    )
    assert "purchases.product_code = 'PREMIUM_30'" in compile_statement(product_session.statement)

    credited_session = RecordingSession(_ScalarResult(5))
    assert (
        await PurchasesRepo.count_credited_product(
            credited_session,
            user_id=7,
            product_code="PREMIUM_30",
        )
        == 5
    )
    assert "purchases.status = 'CREDITED'" in compile_statement(credited_session.statement)

    uncredited_session = RecordingSession(_ScalarResult(6))
    assert (
        await PurchasesRepo.count_paid_uncredited_older_than(
            uncredited_session,
            older_than_utc=since_utc,
        )
        == 6
    )
    assert "purchases.status = 'PAID_UNCREDITED'" in compile_statement(uncredited_session.statement)

    paid_count_session = RecordingSession(_ScalarResult(8))
    assert await PurchasesRepo.count_paid_purchases(paid_count_session) == 8
    assert "purchases.paid_at IS NOT NULL" in compile_statement(paid_count_session.statement)

    stars_session = RecordingSession(_ScalarResult(900))
    assert await PurchasesRepo.sum_paid_stars_amount(stars_session) == 900

    by_product_session = RecordingSession(_RowsResult([("PREMIUM_30", 300), ("ENERGY", None)]))
    totals = await PurchasesRepo.sum_paid_stars_amount_by_product(by_product_session)
    assert totals == {"PREMIUM_30": 300, "ENERGY": 0}
    assert "GROUP BY purchases.product_code" in compile_statement(by_product_session.statement)


async def test_create_sets_created_at_and_flushes_purchase() -> None:
    purchase = _purchase()
    created_at = datetime(2026, 3, 15, 9, 30, tzinfo=UTC)
    session = RecordingSession()

    created = await PurchasesRepo.create(session, purchase=purchase, created_at=created_at)

    assert created is purchase
    assert purchase.created_at == created_at
    assert session.added == [purchase]
    assert session.flushed is True
