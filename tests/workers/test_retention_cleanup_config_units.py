from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from app.workers.tasks import retention_cleanup_runtime as runtime
from app.workers.tasks import retention_cleanup_settings as settings
from app.workers.tasks import retention_cleanup_tables as tables


def test_retention_setting_clamps_cover_bounds_and_swapped_sleep_range() -> None:
    assert settings.clamp_retention_days(0) == 1
    assert settings.clamp_retention_days(9999) == 3650
    assert settings.clamp_batch_size(0) == 1
    assert settings.clamp_batch_size(999999) == 50000
    assert settings.clamp_max_batches(0) == 1
    assert settings.clamp_max_batches(5000) == 1000
    assert settings.clamp_schedule_seconds(-1) == 0
    assert settings.clamp_schedule_seconds(999999) == 86400
    assert settings.clamp_runtime_seconds(1) == 5
    assert settings.clamp_runtime_seconds(999) == 600
    assert settings.resolve_sleep_range_ms(minimum=4000, maximum=25) == (25, 4000)
    assert settings.clamp_schedule_hour(99) == 23
    assert settings.clamp_schedule_minute(99) == 59


def test_resolve_cleanup_schedule_supports_interval_and_crontab() -> None:
    interval_settings = SimpleNamespace(
        retention_cleanup_schedule_seconds=30,
        retention_cleanup_schedule_hour_berlin=25,
        retention_cleanup_schedule_minute_berlin=70,
    )
    cron_settings = SimpleNamespace(
        retention_cleanup_schedule_seconds=0,
        retention_cleanup_schedule_hour_berlin=25,
        retention_cleanup_schedule_minute_berlin=70,
    )

    assert settings.resolve_cleanup_schedule(interval_settings) == 30
    schedule = cast(Any, settings.resolve_cleanup_schedule(cron_settings))
    assert schedule.hour == {23}
    assert schedule.minute == {59}


def test_build_cleanup_config_applies_all_clamps() -> None:
    config = runtime.build_cleanup_config(
        cast(
            Any,
            SimpleNamespace(
                retention_cleanup_batch_size=0,
                retention_cleanup_max_batches_per_table=2000,
                retention_cleanup_max_runtime_seconds=1,
                retention_cleanup_batch_sleep_min_ms=100,
                retention_cleanup_batch_sleep_max_ms=50,
            ),
        )
    )

    assert config == runtime.CleanupConfig(
        batch_size=1,
        max_batches_per_table=1000,
        max_runtime_seconds=5,
        sleep_range_ms=(50, 100),
    )


def test_build_cleanup_table_specs_clamps_retention_and_wires_delete_functions(
    monkeypatch,
) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        tables.ProcessedUpdatesRepo,
        "delete_processed_before",
        _delete_recorder(calls, "processed"),
    )
    monkeypatch.setattr(
        tables.OutboxEventsRepo,
        "delete_created_before",
        _delete_recorder(calls, "outbox"),
    )
    monkeypatch.setattr(
        tables.AnalyticsRepo,
        "delete_events_created_before",
        _delete_recorder(calls, "analytics"),
    )
    specs = tables.build_cleanup_table_specs(
        settings=cast(
            Any,
            SimpleNamespace(
                retention_processed_updates_days=0,
                retention_outbox_events_days=4000,
                retention_analytics_events_days=7,
            ),
        ),
        now_utc=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
    )

    assert [spec.table_name for spec in specs] == [
        "processed_updates",
        "outbox_events",
        "analytics_events",
    ]
    assert [spec.retention_days for spec in specs] == [1, 3650, 7]


def _delete_recorder(target: list[tuple[str, int]], name: str):
    async def _inner(_session, *, cutoff_utc, limit: int) -> int:
        del cutoff_utc
        target.append((name, limit))
        return limit

    return _inner
