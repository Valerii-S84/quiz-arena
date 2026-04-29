from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo import promo_repo_redemptions
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult
from tests.type_helpers import build_promo_code, build_promo_redemption

UTC = timezone.utc


async def test_redemption_lookup_methods_use_expected_filters_and_locks() -> None:
    redemption = build_promo_redemption()
    get_session = RecordingSession(get_result=redemption)

    assert (
        await promo_repo_redemptions.get_redemption_by_id(get_session, redemption.id) is redemption
    )
    assert get_session.get_calls == [(PromoRedemption, redemption.id)]

    lock_session = RecordingSession(_ScalarResult(None))
    await promo_repo_redemptions.get_redemption_by_id_for_update(lock_session, redemption.id)
    assert lock_session.statement is not None
    assert "FOR UPDATE" in compile_statement(lock_session.statement)

    idempotency_session = RecordingSession(_ScalarResult(None))
    await promo_repo_redemptions.get_redemption_by_idempotency_key(
        idempotency_session,
        "promo:key",
    )
    assert idempotency_session.statement is not None
    assert "promo_redemptions.idempotency_key = 'promo:key'" in compile_statement(
        idempotency_session.statement
    )

    idempotency_lock_session = RecordingSession(_ScalarResult(None))
    await promo_repo_redemptions.get_redemption_by_idempotency_key_for_update(
        idempotency_lock_session,
        "promo:key",
    )
    assert idempotency_lock_session.statement is not None
    assert "FOR UPDATE" in compile_statement(idempotency_lock_session.statement)

    user_session = RecordingSession(_ScalarResult(None))
    await promo_repo_redemptions.get_redemption_by_code_and_user_for_update(
        user_session,
        promo_code_id=21,
        user_id=7,
    )
    assert user_session.statement is not None
    user_sql = compile_statement(user_session.statement)
    assert "promo_redemptions.promo_code_id = 21" in user_sql
    assert "promo_redemptions.user_id = 7" in user_sql
    assert "ORDER BY promo_redemptions.updated_at DESC, promo_redemptions.id DESC" in user_sql
    assert "FOR UPDATE" in user_sql


async def test_revoke_redemption_for_refund_updates_active_redemption_and_locks_promo() -> None:
    purchase_id = uuid4()
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    redemption = build_promo_redemption(
        status="APPLIED",
        applied_purchase_id=purchase_id,
        updated_at=datetime(2026, 3, 13, tzinfo=UTC),
    )
    promo = build_promo_code(id=21)
    session = RecordingSession(_ScalarResult(redemption), _ScalarResult(promo))

    result_redemption, result_promo, was_revoked = (
        await promo_repo_redemptions.revoke_redemption_for_refund(
            session,
            purchase_id=purchase_id,
            promo_code_id=21,
            now_utc=now_utc,
        )
    )

    assert result_redemption is redemption
    assert result_promo is promo
    assert was_revoked is True
    assert redemption.status == "REVOKED"
    assert redemption.updated_at == now_utc
    assert len(session.statements) == 2
    assert "promo_redemptions.applied_purchase_id" in compile_statement(session.statements[0])
    assert "promo_codes.id = 21" in compile_statement(session.statements[1])


async def test_refunded_purchase_ids_query_filters_pending_revoke_and_drops_nulls() -> None:
    purchase_id = uuid4()
    session = RecordingSession(_ScalarsResult([purchase_id, None]))

    rows = await promo_repo_redemptions.get_refunded_purchase_ids_with_pending_redemption_revoke(
        session,
        limit=15,
    )

    assert rows == [purchase_id]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "JOIN purchases ON purchases.id = promo_redemptions.applied_purchase_id" in sql
    assert "promo_redemptions.status != 'REVOKED'" in sql
    assert "purchases.status = 'REFUNDED'" in sql
    assert "purchases.applied_promo_code_id IS NOT NULL" in sql
    assert "LIMIT 15" in sql


async def test_redemption_list_count_create_and_expire_paths() -> None:
    redemption = build_promo_redemption(promo_code_id=21, user_id=7)

    list_session = RecordingSession(_ScalarsResult([redemption]))
    rows = await promo_repo_redemptions.list_redemptions_by_code_and_user_for_update(
        list_session,
        promo_code_id=21,
        user_id=7,
    )
    assert rows == [redemption]
    assert list_session.statement is not None
    list_sql = compile_statement(list_session.statement)
    assert "promo_redemptions.promo_code_id = 21" in list_sql
    assert "promo_redemptions.user_id = 7" in list_sql
    assert "FOR UPDATE" in list_sql

    count_session = RecordingSession(_ScalarResult(2))
    assert (
        await promo_repo_redemptions.count_redemptions_by_code_and_user(
            count_session,
            promo_code_id=21,
            user_id=7,
        )
        == 2
    )

    reserved_session = RecordingSession(_ScalarResult(3))
    exclude_id = uuid4()
    assert (
        await promo_repo_redemptions.count_active_reserved_redemptions(
            reserved_session,
            promo_code_id=21,
            now_utc=datetime(2026, 3, 14, tzinfo=UTC),
            exclude_redemption_id=exclude_id,
        )
        == 3
    )
    assert reserved_session.statement is not None
    reserved_sql = compile_statement(reserved_session.statement)
    assert "promo_redemptions.status = 'RESERVED'" in reserved_sql
    assert str(exclude_id) in reserved_sql

    expire_session = RecordingSession(SimpleNamespace(rowcount=4))
    assert (
        await promo_repo_redemptions.expire_reserved_redemptions(
            expire_session,
            now_utc=datetime(2026, 3, 14, tzinfo=UTC),
        )
        == 4
    )
    assert expire_session.statement is not None
    assert "status='EXPIRED'" in compile_statement(expire_session.statement)

    create_session = RecordingSession()
    assert (
        await promo_repo_redemptions.create_redemption(
            create_session,
            redemption=redemption,
        )
        is redemption
    )
    assert create_session.added == [redemption]
    assert create_session.flushed is True
