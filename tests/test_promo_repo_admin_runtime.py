from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.db.repo.promo_repo_admin_runtime import (
    AdminRuntimePromoRepo,
    _search_condition,
    _status_condition,
)
from app.db.repo.promo_repo_admin_runtime_redemptions import (
    list_recent_redemptions,
    revoke_active_reserved_redemptions,
)

UTC = timezone.utc


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class _RowsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._rows)


class _RecordingSession:
    def __init__(self, result) -> None:
        self.statement = None
        self._result = result

    async def execute(self, statement):
        self.statement = statement
        return self._result


def _compile_sql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


async def test_status_condition_compiles_active_inactive_and_expired_filters() -> None:
    now_utc = datetime(2026, 3, 13, tzinfo=UTC)

    active_sql = _compile_sql(_status_condition(status="active", now_utc=now_utc))
    inactive_sql = _compile_sql(_status_condition(status="inactive", now_utc=now_utc))
    expired_sql = _compile_sql(_status_condition(status="expired", now_utc=now_utc))

    assert "promo_codes.status = 'ACTIVE'" in active_sql
    assert "promo_codes.valid_until >" in active_sql
    assert "promo_codes.used_total < promo_codes.max_total_uses" in active_sql
    assert inactive_sql == "promo_codes.status = 'PAUSED'"
    assert "promo_codes.status IN ('EXPIRED', 'DEPLETED')" in expired_sql
    assert "promo_codes.valid_until <=" in expired_sql
    assert "promo_codes.used_total >= promo_codes.max_total_uses" in expired_sql


async def test_search_condition_uses_trimmed_ilike_term() -> None:
    assert _search_condition(query=None) is None

    sql = _compile_sql(_search_condition(query="  spring  "))

    assert "promo_codes.code_prefix ILIKE '%%spring%%'" in sql
    assert "promo_codes.campaign_name ILIKE '%%spring%%'" in sql


async def test_list_existing_hashes_returns_empty_set_without_query() -> None:
    result = await AdminRuntimePromoRepo.list_existing_hashes(object(), code_hashes=())
    assert result == set()


async def test_count_codes_applies_status_and_search_filters() -> None:
    now_utc = datetime(2026, 3, 13, tzinfo=UTC)
    session = _RecordingSession(_ScalarResult(4))

    count = await AdminRuntimePromoRepo.count_codes(
        session,
        status="active",
        query="sale",
        now_utc=now_utc,
    )

    assert count == 4
    assert session.statement is not None

    sql = _compile_sql(session.statement)
    assert "count(promo_codes.id)" in sql
    assert "promo_codes.status = 'ACTIVE'" in sql
    assert "promo_codes.campaign_name ILIKE '%%sale%%'" in sql


async def test_list_codes_clamps_page_and_limit_and_orders_by_recent_update() -> None:
    session = _RecordingSession(_RowsResult([]))
    now_utc = datetime(2026, 3, 13, tzinfo=UTC)

    rows = await AdminRuntimePromoRepo.list_codes(
        session,
        status="expired",
        query="promo",
        page=0,
        limit=999,
        now_utc=now_utc,
    )

    assert rows == []
    assert session.statement is not None

    sql = _compile_sql(session.statement)
    assert "ORDER BY promo_codes.updated_at DESC, promo_codes.id DESC" in sql
    assert "LIMIT 200" in sql
    assert "OFFSET 0" in sql
    assert "promo_codes.valid_until <=" in sql
    assert "promo_codes.campaign_name ILIKE '%%promo%%'" in sql


async def test_list_recent_redemptions_clamps_limit_and_joins_purchase_product() -> None:
    session = _RecordingSession(_RowsResult([]))

    rows = await list_recent_redemptions(session, promo_id=91, limit=500)

    assert rows == []
    assert session.statement is not None

    sql = _compile_sql(session.statement)
    assert "LEFT OUTER JOIN purchases" in sql
    assert "promo_redemptions.promo_code_id = 91" in sql
    assert "LIMIT 100" in sql


async def test_revoke_active_reserved_redemptions_updates_rows_in_memory() -> None:
    now_utc = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)
    row = SimpleNamespace(
        status="RESERVED",
        reserved_until=now_utc.replace(hour=14),
        updated_at=None,
    )
    session = _RecordingSession(_RowsResult([row]))

    rows = await revoke_active_reserved_redemptions(session, promo_id=77, now_utc=now_utc)

    assert rows == [row]
    assert row.status == "REVOKED"
    assert row.reserved_until == now_utc
    assert row.updated_at == now_utc
    assert session.statement is not None

    sql = _compile_sql(session.statement)
    assert "promo_redemptions.status = 'RESERVED'" in sql
    assert "promo_redemptions.reserved_until >" in sql
    assert "FOR UPDATE" in sql
