from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.db.models.promo_codes import PromoCode
from app.db.repo import promo_repo_codes
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult
from tests.type_helpers import build_promo_code

UTC = timezone.utc


async def test_code_lookup_methods_use_expected_filters_and_locks() -> None:
    promo = build_promo_code(id=77)
    get_session = RecordingSession(get_result=promo)

    assert await promo_repo_codes.get_code_by_id(get_session, 77) is promo
    assert get_session.get_calls == [(PromoCode, 77)]

    hash_session = RecordingSession(_ScalarResult(None))
    assert await promo_repo_codes.get_code_by_hash(hash_session, "hash-1") is None
    assert hash_session.statement is not None
    assert "promo_codes.code_hash = 'hash-1'" in compile_statement(hash_session.statement)

    hash_lock_session = RecordingSession(_ScalarResult(None))
    await promo_repo_codes.get_code_by_hash_for_update(hash_lock_session, "hash-2")
    assert hash_lock_session.statement is not None
    assert "FOR UPDATE" in compile_statement(hash_lock_session.statement)

    id_lock_session = RecordingSession(_ScalarResult(None))
    await promo_repo_codes.get_code_by_id_for_update(id_lock_session, 77)
    assert id_lock_session.statement is not None
    id_lock_sql = compile_statement(id_lock_session.statement)
    assert "promo_codes.id = 77" in id_lock_sql
    assert "FOR UPDATE" in id_lock_sql


async def test_list_codes_applies_optional_filters_and_ordering() -> None:
    promo = build_promo_code(id=78)
    session = RecordingSession(_ScalarsResult([promo]))

    rows = await promo_repo_codes.list_codes(
        session,
        status="ACTIVE",
        campaign_name="spring",
        limit=25,
    )

    assert rows == [promo]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "promo_codes.status = 'ACTIVE'" in sql
    assert "promo_codes.campaign_name ILIKE '%%spring%%'" in sql
    assert "ORDER BY promo_codes.updated_at DESC, promo_codes.id DESC" in sql
    assert "LIMIT 25" in sql


async def test_code_maintenance_updates_and_counts_use_expected_predicates() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

    expire_session = RecordingSession(SimpleNamespace(rowcount=2))
    assert await promo_repo_codes.expire_active_codes(expire_session, now_utc=now_utc) == 2
    assert expire_session.statement is not None
    expire_sql = compile_statement(expire_session.statement)
    assert "promo_codes.status = 'ACTIVE'" in expire_sql
    assert "promo_codes.valid_until <=" in expire_sql
    assert "status='EXPIRED'" in expire_sql

    deplete_session = RecordingSession(SimpleNamespace(rowcount=3))
    assert await promo_repo_codes.deplete_active_codes(deplete_session, now_utc=now_utc) == 3
    assert deplete_session.statement is not None
    deplete_sql = compile_statement(deplete_session.statement)
    assert "promo_codes.max_total_uses IS NOT NULL" in deplete_sql
    assert "promo_codes.used_total >= promo_codes.max_total_uses" in deplete_sql
    assert "status='DEPLETED'" in deplete_sql

    status_session = RecordingSession(_RowsResult([("ACTIVE", 5), ("PAUSED", 1)]))
    assert await promo_repo_codes.count_campaigns_by_status(status_session) == {
        "ACTIVE": 5,
        "PAUSED": 1,
    }
    assert status_session.statement is not None
    assert "GROUP BY promo_codes.status" in compile_statement(status_session.statement)

    paused_session = RecordingSession(_ScalarResult(4))
    assert (
        await promo_repo_codes.count_paused_campaigns_since(
            paused_session,
            since_utc=now_utc,
        )
        == 4
    )
    assert paused_session.statement is not None
    assert "promo_codes.status = 'PAUSED'" in compile_statement(paused_session.statement)


async def test_pause_active_codes_by_hashes_short_circuits_empty_and_updates_active_rows() -> None:
    no_execute_session = RecordingSession()
    assert (
        await promo_repo_codes.pause_active_codes_by_hashes(
            no_execute_session,
            code_hashes=[],
            now_utc=datetime(2026, 3, 14, tzinfo=UTC),
        )
        == 0
    )
    assert no_execute_session.statements == []

    pause_session = RecordingSession(SimpleNamespace(rowcount=2))
    changed = await promo_repo_codes.pause_active_codes_by_hashes(
        pause_session,
        code_hashes=["hash-a", "hash-b"],
        now_utc=datetime(2026, 3, 14, tzinfo=UTC),
    )

    assert changed == 2
    assert pause_session.statement is not None
    sql = compile_statement(pause_session.statement)
    assert "promo_codes.code_hash IN ('hash-a', 'hash-b')" in sql
    assert "promo_codes.status = 'ACTIVE'" in sql
    assert "status='PAUSED'" in sql
