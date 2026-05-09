from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.workers.tasks import retention_cleanup_runtime as runtime
from app.workers.tasks.retention_cleanup_tables import CleanupTableSpec
from tests.workers.payments_reliability_async_support import SessionLocalStub

NOW_UTC = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)


def test_build_cleanup_result_and_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[dict[str, object]] = []
    infos: list[dict[str, object]] = []
    monkeypatch.setattr(runtime.logger, "warning", lambda event, **kwargs: warnings.append(kwargs))
    monkeypatch.setattr(runtime.logger, "info", lambda event, **kwargs: infos.append(kwargs))
    config = runtime.CleanupConfig(10, 2, 30, (0, 0))
    result = runtime.build_cleanup_result(
        now_utc=NOW_UTC,
        config=config,
        table_results=[{"rows_deleted": 3}],
        total_rows_deleted=3,
        total_errors=1,
    )

    runtime.log_cleanup_result(result)
    assert result["rows_deleted_total"] == 3
    assert warnings[0]["error_count"] == 1

    runtime.log_cleanup_result({**result, "error_count": 0})
    assert infos[0]["rows_deleted_total"] == 3


@pytest.mark.asyncio
async def test_cleanup_table_batched_stops_when_batch_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"delete": 0}

    async def _delete(_session, _cutoff, _batch_size) -> int:
        calls["delete"] += 1
        return 2

    monkeypatch.setattr(runtime, "SessionLocal", SessionLocalStub())
    spec = _spec(delete_batch_fn=_delete)
    config = runtime.CleanupConfig(10, 3, 30, (0, 0))

    result = await runtime.cleanup_table_batched(spec=spec, config=config)

    assert result["rows_deleted"] == 2
    assert result["batches_executed"] == 1
    assert not result["stopped_by_runtime_guard"]


@pytest.mark.asyncio
async def test_cleanup_table_batched_sleeps_between_full_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    deletes = iter([10, 0])

    async def _delete(_session, _cutoff, _batch_size) -> int:
        return next(deletes)

    monkeypatch.setattr(runtime, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(runtime.asyncio, "sleep", _append_sleep(sleeps))
    spec = _spec(delete_batch_fn=_delete)
    config = runtime.CleanupConfig(10, 3, 30, (5, 5))

    result = await runtime.cleanup_table_batched(spec=spec, config=config)

    assert result["rows_deleted"] == 10
    assert result["batches_executed"] == 2
    assert sleeps == [0.005]


@pytest.mark.asyncio
async def test_run_cleanup_table_returns_failed_result() -> None:
    async def _delete(_session, _cutoff, _batch_size) -> int:
        raise RuntimeError("delete failed")

    result, failed = await runtime.run_cleanup_table(
        spec=_spec(delete_batch_fn=_delete),
        config=runtime.CleanupConfig(10, 1, 30, (0, 0)),
    )

    assert failed
    assert result["error_count"] == 1
    assert result["error"] == "delete failed"


@pytest.mark.asyncio
async def test_run_cleanup_tables_sums_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run_cleanup_table(*, spec, config):
        del spec, config
        return {"rows_deleted": "bad-value"}, False

    monkeypatch.setattr(runtime, "run_cleanup_table", _run_cleanup_table)

    results, rows_deleted, errors = await runtime.run_cleanup_tables(
        specs=(_spec(delete_batch_fn=lambda *_args: 0),),
        config=runtime.CleanupConfig(10, 1, 30, (0, 0)),
    )

    assert len(results) == 1
    assert rows_deleted == 0
    assert errors == 0


def _spec(*, delete_batch_fn) -> CleanupTableSpec:
    return CleanupTableSpec(
        table_name="events",
        retention_days=7,
        cutoff_utc=NOW_UTC,
        delete_batch_fn=delete_batch_fn,
    )


def _append_sleep(target: list[float]):
    async def _inner(seconds: float) -> None:
        target.append(seconds)

    return _inner
