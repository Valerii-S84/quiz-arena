from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.economy.energy.energy_consume_results import (
    build_consume_result,
    build_quiz_debit_entry,
    emit_energy_zero_event_if_needed,
)
from app.economy.energy.energy_daily_topup import apply_daily_topup_berlin
from app.economy.energy.energy_models import (
    apply_snapshot_to_model,
    get_or_create_state_for_update,
    snapshot_from_model,
)
from app.economy.energy.energy_regen import apply_regen_tick
from app.economy.energy.rules import classify_energy_state, consume_quiz_energy
from app.economy.energy.types import EnergyBucketState, EnergyConsumeResult, EnergySnapshot


@dataclass(frozen=True, slots=True)
class _AllowedConsumeRequest:
    state: Any
    user_id: int
    consumed_asset: str | None
    snapshot: EnergySnapshot
    before_state: EnergyBucketState
    idempotency_key: str
    now_utc: datetime


async def consume_quiz(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
) -> EnergyConsumeResult:
    state = await get_or_create_state_for_update(session, user_id, now_utc)
    existing_entry = await LedgerRepo.get_by_idempotency_key(session, idempotency_key)
    premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
    snapshot = snapshot_from_model(state)

    if premium_active:
        return _build_premium_consume_result(snapshot, existing_entry=existing_entry)

    snapshot = _apply_available_energy_updates(
        snapshot,
        now_utc=now_utc,
        premium_active=premium_active,
    )
    before_state = classify_energy_state(snapshot, premium_active=premium_active)

    if existing_entry is not None:
        return await _complete_idempotent_replay(
            session,
            state=state,
            snapshot=snapshot,
            now_utc=now_utc,
            consumed_asset=existing_entry.asset,
        )

    snapshot_after_consume, allowed, consumed_asset = consume_quiz_energy(
        snapshot,
        premium_active=premium_active,
    )
    if not allowed:
        return await _complete_blocked_consume(
            session,
            state=state,
            snapshot=snapshot_after_consume,
            now_utc=now_utc,
        )

    return await _complete_allowed_consume(
        session,
        request=_AllowedConsumeRequest(
            state=state,
            user_id=user_id,
            consumed_asset=consumed_asset,
            snapshot=snapshot_after_consume,
            before_state=before_state,
            idempotency_key=idempotency_key,
            now_utc=now_utc,
        ),
    )


async def _complete_allowed_consume(
    session: AsyncSession,
    *,
    request: _AllowedConsumeRequest,
) -> EnergyConsumeResult:
    await _record_quiz_debit(
        session,
        user_id=request.user_id,
        consumed_asset=request.consumed_asset,
        snapshot=request.snapshot,
        idempotency_key=request.idempotency_key,
        now_utc=request.now_utc,
    )
    apply_snapshot_to_model(request.state, request.snapshot, request.now_utc)
    await session.flush()
    after_state = classify_energy_state(request.snapshot, premium_active=False)
    await emit_energy_zero_event_if_needed(
        session,
        user_id=request.user_id,
        consumed_asset=request.consumed_asset,
        before_state=request.before_state,
        after_state=after_state,
        now_utc=request.now_utc,
    )
    return build_consume_result(
        snapshot=request.snapshot,
        premium_active=False,
        allowed=True,
        idempotent_replay=False,
        consumed_asset=request.consumed_asset,
    )


def _build_premium_consume_result(
    snapshot: EnergySnapshot,
    *,
    existing_entry: Any | None,
) -> EnergyConsumeResult:
    return build_consume_result(
        snapshot=snapshot,
        premium_active=True,
        allowed=True,
        idempotent_replay=existing_entry is not None,
        consumed_asset=existing_entry.asset if existing_entry is not None else "PREMIUM",
    )


def _apply_available_energy_updates(
    snapshot: EnergySnapshot,
    *,
    now_utc: datetime,
    premium_active: bool,
) -> EnergySnapshot:
    snapshot, _ = apply_regen_tick(snapshot, now_utc=now_utc, premium_active=premium_active)
    snapshot, _ = apply_daily_topup_berlin(snapshot, now_utc=now_utc)
    return snapshot


async def _complete_idempotent_replay(
    session: AsyncSession,
    *,
    state: Any,
    snapshot: EnergySnapshot,
    now_utc: datetime,
    consumed_asset: str | None,
) -> EnergyConsumeResult:
    apply_snapshot_to_model(state, snapshot, now_utc)
    await session.flush()
    return build_consume_result(
        snapshot=snapshot,
        premium_active=False,
        allowed=True,
        idempotent_replay=True,
        consumed_asset=consumed_asset,
    )


async def _complete_blocked_consume(
    session: AsyncSession,
    *,
    state: Any,
    snapshot: EnergySnapshot,
    now_utc: datetime,
) -> EnergyConsumeResult:
    apply_snapshot_to_model(state, snapshot, now_utc)
    await session.flush()
    return build_consume_result(
        snapshot=snapshot,
        premium_active=False,
        allowed=False,
        idempotent_replay=False,
        consumed_asset=None,
    )


async def _record_quiz_debit(
    session: AsyncSession,
    *,
    user_id: int,
    consumed_asset: str | None,
    snapshot: EnergySnapshot,
    idempotency_key: str,
    now_utc: datetime,
) -> None:
    ledger_entry = build_quiz_debit_entry(
        user_id=user_id,
        consumed_asset=consumed_asset,
        snapshot=snapshot,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    if ledger_entry is None:
        return
    await LedgerRepo.create(session, entry=ledger_entry)
