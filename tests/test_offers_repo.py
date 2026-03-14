from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.db.repo.offers_repo import OffersRepo

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


async def test_get_by_idempotency_key_filters_by_user_and_key() -> None:
    session = _RecordingSession(_ScalarResult(None))

    result = await OffersRepo.get_by_idempotency_key(
        session,
        user_id=7,
        idempotency_key="offer:abc",
    )

    assert result is None
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "offers_impressions.user_id = 7" in sql
    assert "offers_impressions.idempotency_key = 'offer:abc'" in sql


async def test_list_for_user_since_orders_most_recent_first() -> None:
    session = _RecordingSession(_RowsResult([]))
    shown_since_utc = datetime(2026, 3, 10, tzinfo=UTC)

    rows = await OffersRepo.list_for_user_since(
        session,
        user_id=8,
        shown_since_utc=shown_since_utc,
    )

    assert rows == []
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "offers_impressions.user_id = 8" in sql
    assert "offers_impressions.shown_at >=" in sql
    assert "ORDER BY offers_impressions.shown_at DESC" in sql


async def test_insert_impression_if_absent_uses_on_conflict_do_nothing() -> None:
    session = _RecordingSession(_ScalarResult(55))
    shown_at = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)

    result = await OffersRepo.insert_impression_if_absent(
        session,
        user_id=9,
        offer_code="OFFER_ENERGY_ZERO",
        trigger_code="TRG_ENERGY_ZERO",
        priority=100,
        shown_at=shown_at,
        local_date_berlin=shown_at.date(),
        idempotency_key="offer:impression:1",
    )

    assert result == 55
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "INSERT INTO offers_impressions" in sql
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in sql
    assert "RETURNING offers_impressions.id" in sql


async def test_mark_clicked_requires_not_clicked_and_not_dismissed() -> None:
    session = _RecordingSession(SimpleNamespace(rowcount=1))
    clicked_at = datetime(2026, 3, 13, 13, 0, tzinfo=UTC)

    changed = await OffersRepo.mark_clicked(
        session,
        user_id=5,
        impression_id=77,
        clicked_at=clicked_at,
    )

    assert changed is True
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "offers_impressions.id = 77" in sql
    assert "offers_impressions.user_id = 5" in sql
    assert "offers_impressions.clicked_at IS NULL" in sql
    assert "offers_impressions.dismiss_reason IS NULL" in sql


async def test_mark_converted_purchase_requires_missing_existing_conversion() -> None:
    session = _RecordingSession(SimpleNamespace(rowcount=1))
    purchase_id = uuid4()

    changed = await OffersRepo.mark_converted_purchase(
        session,
        user_id=11,
        impression_id=81,
        purchase_id=purchase_id,
    )

    assert changed is True
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "offers_impressions.converted_purchase_id IS NULL" in sql
    assert str(purchase_id) in sql


async def test_offer_aggregate_queries_apply_expected_filters() -> None:
    shown_since_utc = datetime(2026, 3, 1, tzinfo=UTC)

    count_clicked_session = _RecordingSession(_ScalarResult(2))
    count_dismissed_session = _RecordingSession(_ScalarResult(3))
    count_converted_session = _RecordingSession(_ScalarResult(4))
    by_offer_session = _RecordingSession(_RowsResult([("OFFER_A", 5), ("OFFER_B", 1)]))

    assert (
        await OffersRepo.count_clicked_since(
            count_clicked_session,
            shown_since_utc=shown_since_utc,
        )
        == 2
    )
    assert (
        await OffersRepo.count_dismissed_since(
            count_dismissed_session,
            shown_since_utc=shown_since_utc,
        )
        == 3
    )
    assert (
        await OffersRepo.count_converted_since(
            count_converted_session,
            shown_since_utc=shown_since_utc,
        )
        == 4
    )
    assert await OffersRepo.count_impressions_by_offer_code_since(
        by_offer_session,
        shown_since_utc=shown_since_utc,
        limit=10,
    ) == {"OFFER_A": 5, "OFFER_B": 1}

    assert "offers_impressions.clicked_at IS NOT NULL" in _compile_sql(
        count_clicked_session.statement
    )
    assert "offers_impressions.dismiss_reason IS NULL" in _compile_sql(
        count_clicked_session.statement
    )
    assert "offers_impressions.dismiss_reason IS NOT NULL" in _compile_sql(
        count_dismissed_session.statement
    )
    assert "offers_impressions.converted_purchase_id IS NOT NULL" in _compile_sql(
        count_converted_session.statement
    )
    by_offer_sql = _compile_sql(by_offer_session.statement)
    assert "GROUP BY offers_impressions.offer_code" in by_offer_sql
    assert "ORDER BY count(offers_impressions.id) DESC" in by_offer_sql
