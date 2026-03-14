from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.db.repo import promo_repo_admin_runtime_redemptions as redemptions_repo

UTC = timezone.utc


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values) -> None:
        self._values = values

    def all(self):
        return list(self._values)


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
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


async def test_count_redemptions_by_status_groups_rows() -> None:
    session = _RecordingSession(_RowsResult([("APPLIED", 3), ("RESERVED", 1)]))

    result = await redemptions_repo.count_redemptions_by_status(session, promo_id=44)

    assert result == {"APPLIED": 3, "RESERVED": 1}
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "promo_redemptions.promo_code_id = 44" in sql
    assert "GROUP BY promo_redemptions.status" in sql


async def test_count_active_reserved_redemptions_filters_future_reservations() -> None:
    now_utc = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)
    session = _RecordingSession(_ScalarResult(2))

    count = await redemptions_repo.count_active_reserved_redemptions(
        session,
        promo_id=55,
        now_utc=now_utc,
    )

    assert count == 2
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "promo_redemptions.status = 'RESERVED'" in sql
    assert "promo_redemptions.reserved_until >" in sql


async def test_list_redemptions_clamps_page_and_limit() -> None:
    session = _RecordingSession(_RowsResult([]))

    rows = await redemptions_repo.list_redemptions(
        session,
        promo_id=66,
        page=0,
        limit=999,
    )

    assert rows == []
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "promo_redemptions.promo_code_id = 66" in sql
    assert "LIMIT 200" in sql
    assert "OFFSET 0" in sql
