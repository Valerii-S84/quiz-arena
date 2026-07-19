from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchases import Purchase
from app.db.models.users import User


async def list_stars_reconciliation_candidate_rows(
    session: AsyncSession,
    *,
    transaction_id: str,
    invoice_payload: str | None,
    telegram_user_id: int | None,
    transaction_date: datetime,
    match_window: timedelta,
    limit: int = 20,
    for_update: bool = False,
) -> list[tuple[Purchase, int]]:
    exact_match_conditions = [Purchase.telegram_payment_charge_id == transaction_id]
    match_conditions = list(exact_match_conditions)
    if invoice_payload:
        exact_match_conditions.append(Purchase.invoice_payload == invoice_payload)
        match_conditions.append(Purchase.invoice_payload == invoice_payload)
    if telegram_user_id is not None:
        match_conditions.append(
            and_(
                User.telegram_user_id == telegram_user_id,
                Purchase.created_at >= transaction_date - match_window,
                Purchase.created_at <= transaction_date,
            )
        )

    exact_match_rank = case((or_(*exact_match_conditions), 0), else_=1)
    stmt = (
        select(Purchase, User.telegram_user_id)
        .join(User, User.id == Purchase.user_id)
        .where(Purchase.stars_amount > 0, or_(*match_conditions))
        .order_by(exact_match_rank, Purchase.created_at.desc())
        .limit(limit)
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return [(cast(Purchase, row[0]), int(row[1])) for row in result.all()]
