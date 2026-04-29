from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.admins import Admin
from app.db.repo.admin_audit_repo import AdminAuditRepo
from app.db.repo.admins_repo import AdminsRepo
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from tests.db.repo._helpers import IterableScalarsResult, RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


async def test_admin_repo_creates_updates_and_logs_audit_entries() -> None:
    existing = Admin(email="admin@example.com", role="admin")

    lookup_session = RecordingSession(_ScalarResult(existing))
    assert await AdminsRepo.get_by_email(lookup_session, email="admin@example.com") is existing
    assert "admins.email = 'admin@example.com'" in compile_statement(lookup_session.statement)

    create_session = RecordingSession(_ScalarResult(None))
    created = await AdminsRepo.get_or_create(
        create_session,
        email="new-admin@example.com",
        role="admin",
    )
    assert created.email == "new-admin@example.com"
    assert create_session.added == [created]
    assert create_session.flushed is True

    update_session = RecordingSession(_ScalarResult(existing))
    updated = await AdminsRepo.get_or_create(
        update_session,
        email="admin@example.com",
        role="super_admin",
    )
    assert updated is existing
    assert existing.role == "super_admin"
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
    assert "LIMIT 1" in delete_sql
