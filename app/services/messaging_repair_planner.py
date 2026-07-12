from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.messaging_repair_models import ExistingDeliveryOutcome as ExistingDeliveryOutcome
from app.services.messaging_repair_models import MessagingRepairPlan
from app.services.messaging_repair_models import RepairTarget as RepairTarget
from app.services.messaging_repair_plan_builder import build_messaging_repair_plan
from app.services.messaging_repair_queries import (
    load_delivery_attempts,
    load_tournament_expected_targets,
)


async def plan_tournament_messaging_repair(
    session: AsyncSession,
    *,
    flow: str,
    tournament_id: str,
) -> MessagingRepairPlan:
    if flow not in {"daily_cup_round_messaging", "private_tournament_round_messaging"}:
        raise ValueError("unsupported repair flow")
    expected_targets = await load_tournament_expected_targets(
        session,
        flow=flow,
        tournament_id=tournament_id,
    )
    existing_attempts = await load_delivery_attempts(
        session,
        flow=flow,
        correlation_id=tournament_id,
    )
    return build_messaging_repair_plan(
        flow=flow,
        correlation_id=tournament_id,
        expected_targets=expected_targets,
        existing_attempts=existing_attempts,
    )


__all__ = (
    "ExistingDeliveryOutcome MessagingRepairPlan RepairTarget "
    "build_messaging_repair_plan plan_tournament_messaging_repair"
).split()
