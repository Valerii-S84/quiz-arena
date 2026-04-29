from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.models.promo_audit_log import PromoAuditLog
from app.db.repo.promo_audit_repo import PromoAuditRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


async def test_promo_audit_log_creates_entry_and_flushes() -> None:
    admin_id = uuid4()
    session = RecordingSession()

    entry = await PromoAuditRepo.log(
        session,
        admin_id=admin_id,
        action="created",
        promo_code_id=21,
        details={"status": "ACTIVE"},
    )

    assert session.added == [entry]
    assert session.flushed is True
    assert entry.admin_id == admin_id
    assert entry.action == "created"
    assert entry.promo_code_id == 21
    assert entry.details == {"status": "ACTIVE"}
    assert entry.created_at.tzinfo is not None


async def test_promo_audit_list_for_promo_joins_admin_email_and_orders_recent_first() -> None:
    entry = PromoAuditLog(
        id=uuid4(),
        admin_id=uuid4(),
        action="paused",
        promo_code_id=21,
        details={},
        created_at=datetime(2026, 3, 14, tzinfo=UTC),
    )
    session = RecordingSession(_RowsResult([(entry, "admin@example.com")]))

    rows = await PromoAuditRepo.list_for_promo(session, promo_code_id=21, limit=25)

    assert rows == [(entry, "admin@example.com")]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "JOIN admins ON admins.id = promo_audit_log.admin_id" in sql
    assert "promo_audit_log.promo_code_id = 21" in sql
    assert "ORDER BY promo_audit_log.created_at DESC, promo_audit_log.id DESC" in sql
    assert "LIMIT 25" in sql


async def test_promo_audit_list_for_actions_short_circuits_and_filters_actions() -> None:
    empty_session = RecordingSession()
    assert await PromoAuditRepo.list_for_actions(empty_session, actions=[]) == []
    assert empty_session.statements == []

    entry = PromoAuditLog(
        id=uuid4(),
        admin_id=uuid4(),
        action="created",
        promo_code_id=None,
        details={},
        created_at=datetime(2026, 3, 14, tzinfo=UTC),
    )
    session = RecordingSession(_ScalarsResult([entry]))

    rows = await PromoAuditRepo.list_for_actions(session, actions=["created", "paused"])

    assert rows == [entry]
    assert session.statement is not None
    assert "promo_audit_log.action IN ('created', 'paused')" in compile_statement(session.statement)
