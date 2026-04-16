from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects import postgresql

from app.db.repo import promo_repo_admin_runtime_redemptions as redemptions_repo
from tests.type_helpers import AsyncSessionStub
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


class _RecordingSession(AsyncSessionStub):
    def __init__(self, result) -> None:
        self.statement = None
        self._result = result

    async def execute(self, statement):
        self.statement = statement
        return self._result


def _compile_sql(statement: Any) -> str:
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
    session = _RecordingSession(_ScalarsResult([]))

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
