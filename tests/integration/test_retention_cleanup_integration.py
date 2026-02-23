from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.outbox_events import OutboxEvent
from app.db.models.processed_updates import ProcessedUpdate
from app.db.session import SessionLocal
from app.workers.tasks.retention_cleanup import run_retention_cleanup_async

UTC = timezone.utc


@pytest.mark.asyncio
async def test_retention_cleanup_deletes_only_records_older_than_policy_cutoffs() -> None:
    now_utc = datetime.now(UTC)

    old_processed_update_id = 111_001
    fresh_processed_update_id = 111_002
    old_outbox_event_id = 222_001
    fresh_outbox_event_id = 222_002
    old_analytics_event_id = 333_001
    fresh_analytics_event_id = 333_002

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                ProcessedUpdate(
                    update_id=old_processed_update_id,
                    processed_at=now_utc - timedelta(days=20),
                    status="PROCESSED",
                    processing_task_id=None,
                ),
                ProcessedUpdate(
                    update_id=fresh_processed_update_id,
                    processed_at=now_utc - timedelta(days=2),
                    status="PROCESSED",
                    processing_task_id=None,
                ),
                OutboxEvent(
                    id=old_outbox_event_id,
                    event_type="retention_test_old",
                    payload={"scope": "integration"},
                    status="SENT",
                    created_at=now_utc - timedelta(days=40),
                ),
                OutboxEvent(
                    id=fresh_outbox_event_id,
                    event_type="retention_test_fresh",
                    payload={"scope": "integration"},
                    status="SENT",
                    created_at=now_utc - timedelta(days=3),
                ),
                AnalyticsEvent(
                    id=old_analytics_event_id,
                    event_type="retention_test_old",
                    source="SYSTEM",
                    user_id=None,
                    local_date_berlin=(now_utc - timedelta(days=120)).date(),
                    payload={"scope": "integration"},
                    happened_at=now_utc - timedelta(days=120),
                    created_at=now_utc - timedelta(days=120),
                ),
                AnalyticsEvent(
                    id=fresh_analytics_event_id,
                    event_type="retention_test_fresh",
                    source="SYSTEM",
                    user_id=None,
                    local_date_berlin=(now_utc - timedelta(days=2)).date(),
                    payload={"scope": "integration"},
                    happened_at=now_utc - timedelta(days=2),
                    created_at=now_utc - timedelta(days=2),
                ),
            ]
        )
        await session.flush()

    result = await run_retention_cleanup_async()

    assert int(result["error_count"]) == 0
    table_results = {str(item["table"]): item for item in result["tables"]}
    assert int(table_results["processed_updates"]["rows_deleted"]) == 1
    assert int(table_results["outbox_events"]["rows_deleted"]) == 1
    assert int(table_results["analytics_events"]["rows_deleted"]) == 1
    assert int(result["rows_deleted_total"]) == 3

    async with SessionLocal.begin() as session:
        processed_rows = set(
            (await session.execute(select(ProcessedUpdate.update_id))).scalars().all()
        )
        outbox_rows = set((await session.execute(select(OutboxEvent.id))).scalars().all())
        analytics_rows = set((await session.execute(select(AnalyticsEvent.id))).scalars().all())

    assert old_processed_update_id not in processed_rows
    assert fresh_processed_update_id in processed_rows
    assert old_outbox_event_id not in outbox_rows
    assert fresh_outbox_event_id in outbox_rows
    assert old_analytics_event_id not in analytics_rows
    assert fresh_analytics_event_id in analytics_rows
