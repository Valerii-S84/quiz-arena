from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.promo_codes import PromoCode
from app.db.repo.promo_repo_admin_runtime import AdminRuntimePromoRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult
from tests.type_helpers import build_promo_code

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


async def test_admin_runtime_lookup_methods_use_expected_keys_and_locks() -> None:
    promo = build_promo_code(id=31, code_hash="hash-31")
    get_session = RecordingSession(get_result=promo)

    assert await AdminRuntimePromoRepo.get_by_id(get_session, 31) is promo
    assert get_session.get_calls == [(PromoCode, 31)]

    lock_session = RecordingSession(_ScalarResult(None))
    assert await AdminRuntimePromoRepo.get_by_id_for_update(lock_session, 31) is None
    assert lock_session.statement is not None
    lock_sql = compile_statement(lock_session.statement)
    assert "promo_codes.id = 31" in lock_sql
    assert "FOR UPDATE" in lock_sql

    hash_session = RecordingSession(_ScalarResult(promo))
    assert await AdminRuntimePromoRepo.get_by_hash(hash_session, "hash-31") is promo
    assert hash_session.statement is not None
    assert "promo_codes.code_hash = 'hash-31'" in compile_statement(hash_session.statement)


async def test_admin_runtime_existing_hashes_short_circuit_and_cast_results() -> None:
    empty_session = RecordingSession()
    assert await AdminRuntimePromoRepo.list_existing_hashes(empty_session, code_hashes=[]) == set()
    assert empty_session.statements == []

    session = RecordingSession(_ScalarsResult(["hash-a", "hash-b"]))
    rows = await AdminRuntimePromoRepo.list_existing_hashes(
        session,
        code_hashes=["hash-a", "hash-b"],
    )

    assert rows == {"hash-a", "hash-b"}
    assert session.statement is not None
    assert "promo_codes.code_hash IN ('hash-a', 'hash-b')" in compile_statement(session.statement)


async def test_admin_runtime_create_and_bulk_create_flush_promos() -> None:
    promo = build_promo_code(id=32)
    create_session = RecordingSession()
    assert await AdminRuntimePromoRepo.create(create_session, promo=promo) is promo
    assert create_session.added == [promo]
    assert create_session.flushed is True

    promo_a = build_promo_code(id=33, code_hash="hash-33")
    promo_b = build_promo_code(id=34, code_hash="hash-34")
    bulk_session = RecordingSession()
    created = await AdminRuntimePromoRepo.bulk_create(bulk_session, promos=[promo_a, promo_b])

    assert created == [promo_a, promo_b]
    assert bulk_session.added_all == [promo_a, promo_b]
    assert bulk_session.flushed is True


async def test_admin_runtime_count_codes_applies_active_search_and_inactive_filters() -> None:
    active_session = RecordingSession(_ScalarResult(5))
    assert (
        await AdminRuntimePromoRepo.count_codes(
            active_session,
            status="active",
            query=" spring ",
            now_utc=NOW_UTC,
        )
        == 5
    )
    assert active_session.statement is not None
    active_sql = compile_statement(active_session.statement)
    assert "promo_codes.status = 'ACTIVE'" in active_sql
    assert "promo_codes.valid_until >" in active_sql
    assert "promo_codes.used_total < promo_codes.max_total_uses" in active_sql
    assert "promo_codes.code_prefix ILIKE '%%spring%%'" in active_sql
    assert "promo_codes.campaign_name ILIKE '%%spring%%'" in active_sql

    inactive_session = RecordingSession(_ScalarResult(2))
    assert (
        await AdminRuntimePromoRepo.count_codes(
            inactive_session,
            status="inactive",
            query=None,
            now_utc=NOW_UTC,
        )
        == 2
    )
    inactive_sql = compile_statement(inactive_session.statement)
    assert "promo_codes.status = 'PAUSED'" in inactive_sql
    assert "ILIKE" not in inactive_sql


async def test_admin_runtime_count_codes_allows_search_without_status_filter() -> None:
    session = RecordingSession(_ScalarResult(3))

    assert (
        await AdminRuntimePromoRepo.count_codes(
            session,
            status=None,
            query="PROMO",
            now_utc=NOW_UTC,
        )
        == 3
    )

    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "promo_codes.status" not in sql
    assert "promo_codes.code_prefix ILIKE '%%PROMO%%'" in sql


async def test_admin_runtime_list_codes_clamps_pagination_and_expired_filters() -> None:
    promo = build_promo_code(id=35)
    session = RecordingSession(_ScalarsResult([promo]))

    rows = await AdminRuntimePromoRepo.list_codes(
        session,
        status="expired",
        query="PROMO",
        page=-5,
        limit=500,
        now_utc=NOW_UTC,
    )

    assert rows == [promo]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "promo_codes.status IN ('EXPIRED', 'DEPLETED')" in sql
    assert "promo_codes.valid_until <=" in sql
    assert "promo_codes.used_total >= promo_codes.max_total_uses" in sql
    assert "promo_codes.code_prefix ILIKE '%%PROMO%%'" in sql
    assert "ORDER BY promo_codes.updated_at DESC, promo_codes.id DESC" in sql
    assert "LIMIT 200" in sql
    assert "OFFSET 0" in sql


async def test_admin_runtime_list_codes_allows_unfiltered_pages() -> None:
    session = RecordingSession(_ScalarsResult([]))

    rows = await AdminRuntimePromoRepo.list_codes(
        session,
        status=None,
        query=None,
        page=2,
        limit=0,
        now_utc=NOW_UTC,
    )

    assert rows == []
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "WHERE" not in sql
    assert "LIMIT 1" in sql
    assert "OFFSET 1" in sql
