from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.admins import Admin
from app.db.models.outbox_events import OutboxEvent
from app.db.repo.admin_audit_repo import AdminAuditRepo
from app.db.repo.admins_repo import AdminsRepo
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from tests.db.repo._helpers import IterableScalarsResult, RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


async def test_admin_repo_creates_updates_and_logs_audit_entries() -> None:
    existing = Admin(email="admin@example.com", role="admin", enabled=True)

    lookup_session = RecordingSession(_ScalarResult(existing))
    assert await AdminsRepo.get_by_email(lookup_session, email="admin@example.com") is existing
    lookup_sql = compile_statement(lookup_session.statement)
    assert "lower(trim(admins.email)) = 'admin@example.com'" in lookup_sql

    create_session = RecordingSession(_ScalarResult(None))
    created = await AdminsRepo.get_or_create(
        create_session,
        email="new-admin@example.com",
        role="admin",
    )
    assert created.email == "new-admin@example.com"
    assert created.enabled is False
    assert create_session.added == [created]
    assert create_session.flushed is True

    update_session = RecordingSession(_ScalarResult(existing))
    updated = await AdminsRepo.get_or_create(
        update_session,
        email="admin@example.com",
        role="super_admin",
    )
    assert updated is existing
    assert existing.role == "admin"
    assert existing.enabled is True
    assert update_session.added == []

    audit_session = RecordingSession()
    entry = await AdminAuditRepo.log(
        audit_session,
        admin_email="admin@example.com",
        action="promo.pause",
        target_type="promo",
        target_id="42",
        payload={"reason": "test"},
        ip="127.0.0.1",
    )
    assert entry.action == "promo.pause"
    assert audit_session.added == [entry]
    assert audit_session.flushed is True


async def test_outbox_repo_lists_counts_and_deletes_by_scoped_filters() -> None:
    since_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    event_types = ("promo.applied", "purchase.credited")

    create_session = RecordingSession()
    event = await OutboxEventsRepo.create(
        create_session,
        event_type="promo.applied",
        payload={"promo_code_id": 21},
        status="PENDING",
    )
    assert event.event_type == "promo.applied"
    assert create_session.added == [event]

    list_session = RecordingSession(_ScalarsResult([event]))
    assert await OutboxEventsRepo.list_events_since(
        list_session,
        since_utc=since_utc,
        event_types=event_types,
        limit=25,
    ) == [event]
    list_sql = compile_statement(list_session.statement)
    assert "outbox_events.event_type IN ('promo.applied', 'purchase.credited')" in list_sql
    assert "ORDER BY outbox_events.created_at DESC, outbox_events.id DESC" in list_sql

    status_session = RecordingSession(_RowsResult([("PENDING", 2), ("SENT", 1)]))
    assert await OutboxEventsRepo.count_by_status_since(
        status_session,
        since_utc=since_utc,
        event_types=event_types,
    ) == {"PENDING": 2, "SENT": 1}

    type_session = RecordingSession(_RowsResult([("promo.applied", 3)]))
    assert await OutboxEventsRepo.count_by_type_since(
        type_session,
        since_utc=since_utc,
        event_types=event_types,
    ) == {"promo.applied": 3}

    delete_session = RecordingSession(IterableScalarsResult([1, 2]))
    assert (
        await OutboxEventsRepo.delete_created_before(
            delete_session,
            cutoff_utc=since_utc,
            limit=0,
        )
        == 2
    )
    delete_sql = compile_statement(delete_session.statement)
    assert "DELETE FROM outbox_events" in delete_sql
    assert "outbox_events.status != 'OPEN'" in delete_sql
    assert "LIMIT 1" in delete_sql


async def test_outbox_repo_create_once_locks_and_reuses_duplicate_payload_key() -> None:
    existing = OutboxEvent(
        event_type="payments_telegram_stars_reconciliation_review",
        payload={"review_key": "review-1"},
        status="OPEN",
    )
    reuse_session = RecordingSession(object(), _ScalarResult(existing))

    reused, was_created = await OutboxEventsRepo.create_once_by_payload_key(
        reuse_session,
        event_type="payments_telegram_stars_reconciliation_review",
        payload={"review_key": "review-1"},
        payload_key="review_key",
        status="OPEN",
    )

    assert reused is existing
    assert was_created is False
    assert reuse_session.added == []
    assert "pg_advisory_xact_lock" in str(reuse_session.statements[0])
    lookup_sql = compile_statement(reuse_session.statements[1])
    assert "outbox_events" in lookup_sql
    assert "review_key" in lookup_sql
    assert "review-1" in lookup_sql


async def test_outbox_repo_can_exclude_non_blocking_review_reason() -> None:
    existing = OutboxEvent(
        event_type="payments_telegram_stars_reconciliation_review",
        payload={
            "transaction_id_hash": "tx-hash-1",
            "reason": "AMBIGUOUS_MATCH",
        },
        status="OPEN",
    )
    lookup_session = RecordingSession(_ScalarResult(existing))

    result = await OutboxEventsRepo.get_open_by_payload_key_excluding_reason(
        lookup_session,
        event_type="payments_telegram_stars_reconciliation_review",
        payload_key="transaction_id_hash",
        payload_value="tx-hash-1",
        excluded_reason="WOULD_RECOVER_EXACT_MATCH",
        status="OPEN",
    )

    assert result is existing
    lookup_sql = compile_statement(lookup_session.statement)
    assert "transaction_id_hash" in lookup_sql
    assert "tx-hash-1" in lookup_sql
    assert "reason" in lookup_sql
    assert "WOULD_RECOVER_EXACT_MATCH" in lookup_sql
    assert "!=" in lookup_sql


async def test_outbox_repo_create_once_inserts_after_locked_empty_lookup() -> None:
    create_session = RecordingSession(object(), _ScalarResult(None))

    event, was_created = await OutboxEventsRepo.create_once_by_payload_key(
        create_session,
        event_type="telegram_payment_update_received",
        payload={"payment_update_key": "777:message.successful_payment"},
        payload_key="payment_update_key",
        status="PENDING",
    )

    assert was_created is True
    assert event.event_type == "telegram_payment_update_received"
    assert event.status == "PENDING"
    assert create_session.added == [event]
    assert create_session.flushed is True
    assert "pg_advisory_xact_lock" in str(create_session.statements[0])
