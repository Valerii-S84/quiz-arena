from __future__ import annotations

from sqlalchemy import Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.processed_updates import ProcessedUpdate


def build_processing_age_seconds_expr(*, cast_to_float: bool = False):
    processing_age_seconds = func.extract(
        "epoch",
        func.now() - ProcessedUpdate.processed_at,
    )
    if cast_to_float:
        return processing_age_seconds.cast(Float)
    return processing_age_seconds


async def count_processing_older_than_seconds(
    session: AsyncSession,
    *,
    older_than_seconds: int,
) -> int:
    processing_age_seconds = build_processing_age_seconds_expr()
    stmt = select(func.count(ProcessedUpdate.update_id)).where(
        ProcessedUpdate.status == "PROCESSING",
        processing_age_seconds >= max(1, int(older_than_seconds)),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_processing_age_max_seconds(session: AsyncSession) -> int:
    processing_age_seconds = build_processing_age_seconds_expr(cast_to_float=True)
    stmt = select(func.max(processing_age_seconds)).where(
        ProcessedUpdate.status == "PROCESSING",
    )
    result = await session.execute(stmt)
    raw_age = result.scalar_one_or_none()
    if raw_age is None:
        return 0
    return max(0, int(raw_age))


async def list_oldest_processing(
    session: AsyncSession,
    *,
    limit: int,
) -> list[dict[str, object]]:
    processing_age_seconds = build_processing_age_seconds_expr(cast_to_float=True)
    stmt = (
        select(
            ProcessedUpdate.update_id,
            ProcessedUpdate.processing_task_id,
            ProcessedUpdate.processed_at,
            processing_age_seconds.label("age_seconds"),
        )
        .where(ProcessedUpdate.status == "PROCESSING")
        .order_by(processing_age_seconds.desc(), ProcessedUpdate.update_id.asc())
        .limit(max(1, int(limit)))
    )
    result = await session.execute(stmt)
    return [
        {
            "update_id": int(update_id),
            "processing_task_id": (
                str(processing_task_id) if processing_task_id is not None else None
            ),
            "processed_at": processed_at.isoformat(),
            "age_seconds": max(0, int(age_seconds or 0)),
        }
        for update_id, processing_task_id, processed_at, age_seconds in result.all()
    ]
