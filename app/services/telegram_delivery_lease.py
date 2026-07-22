from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.telegram_delivery_retry_repo import (
    PENDING_REPLAY_SAFE_CONTEXT_KEY,
    RETRY_NEEDED_FAILURE_CODE,
)
from app.services.telegram_delivery_outcomes import TelegramDeliveryOutcome


class TelegramDeliveryCallOptions(TypedDict, total=False):
    allow_pending_replay_send: bool
    allow_stale_pending_replay_send: bool
    pending_replay_claim_attempt_count: int | None
    retry_claim_ttl_seconds: int
    attempts_repo: Any


@dataclass(frozen=True, slots=True)
class TelegramDeliveryReplayPolicy:
    allow_claimed: bool = False
    allow_stale: bool = False
    claim_attempt_count: int | None = None
    ttl_seconds: int = 300


def resolve_call_options(
    options: TelegramDeliveryCallOptions,
) -> tuple[Any, int, TelegramDeliveryReplayPolicy]:
    claim_ttl_seconds = options.get("retry_claim_ttl_seconds", 300)
    replay_policy = TelegramDeliveryReplayPolicy(
        allow_claimed=options.get("allow_pending_replay_send", False),
        allow_stale=options.get("allow_stale_pending_replay_send", False),
        claim_attempt_count=options.get("pending_replay_claim_attempt_count"),
        ttl_seconds=claim_ttl_seconds,
    )
    return options.get("attempts_repo", None), claim_ttl_seconds, replay_policy


@dataclass(frozen=True, slots=True)
class TelegramDeliveryLease:
    created: bool
    replayed: bool
    attempt_count: int | None = None


async def claim_pending_replay(
    *,
    session: AsyncSession,
    row: object,
    policy: TelegramDeliveryReplayPolicy,
    idempotency_key: str,
    attempts_repo: Any,
) -> int | None:
    cas_enabled = lease_cas_enabled(attempts_repo)
    if cas_enabled and not pending_replay_is_safe(row):
        return None
    if policy.allow_claimed:
        if not cas_enabled:
            return row_attempt_count(row, required=False)
        if policy.claim_attempt_count is None:
            return None
        return await _dispatch_pending_replay(
            session=session,
            idempotency_key=idempotency_key,
            expected_attempt_count=policy.claim_attempt_count,
            attempts_repo=attempts_repo,
        )
    if not policy.allow_stale:
        return None
    claimed_attempt_count = await attempts_repo.claim_stale_pending_replay(
        session,
        idempotency_key=idempotency_key,
        claim_ttl_seconds=policy.ttl_seconds,
    )
    if not claimed_attempt_count:
        return None
    if not cas_enabled:
        return row_attempt_count(row, required=False)
    return await _dispatch_pending_replay(
        session=session,
        idempotency_key=idempotency_key,
        expected_attempt_count=int(claimed_attempt_count),
        attempts_repo=attempts_repo,
    )


async def _dispatch_pending_replay(
    *,
    session: AsyncSession,
    idempotency_key: str,
    expected_attempt_count: int,
    attempts_repo: Any,
) -> int:
    dispatched_attempt_count = await attempts_repo.claim_pending_replay_dispatch(
        session,
        idempotency_key=idempotency_key,
        expected_attempt_count=expected_attempt_count,
    )
    if dispatched_attempt_count is None:
        raise RuntimeError("telegram delivery retry lease was lost")
    return int(dispatched_attempt_count)


def pending_replay_is_safe(row: object) -> bool:
    safe_context = getattr(row, "safe_context", None)
    replay_safe = (
        isinstance(safe_context, dict) and safe_context.get(PENDING_REPLAY_SAFE_CONTEXT_KEY) is True
    )
    retry_was_guaranteed_undelivered = (
        getattr(row, "failure_code", None) == RETRY_NEEDED_FAILURE_CODE
    )
    return replay_safe or retry_was_guaranteed_undelivered


def lease_cas_enabled(attempts_repo: Any) -> bool:
    return bool(getattr(attempts_repo, "supports_delivery_lease_cas", False))


def row_attempt_count(row: object, *, required: bool) -> int:
    attempt_count = getattr(row, "attempt_count", None)
    if isinstance(attempt_count, int) and attempt_count > 0:
        return attempt_count
    if required:
        raise RuntimeError("telegram delivery lease token is missing")
    return 1


def lease_update_kwargs(
    prepared: TelegramDeliveryLease,
    attempts_repo: Any,
) -> dict[str, int]:
    if not lease_cas_enabled(attempts_repo):
        return {}
    if prepared.attempt_count is None:
        raise RuntimeError("telegram delivery lease token is missing")
    return {"expected_attempt_count": prepared.attempt_count}


def require_lease_update(*, updated: bool, status: str, attempts_repo: Any) -> None:
    if lease_cas_enabled(attempts_repo) and not updated:
        raise RuntimeError(f"telegram delivery {status} lease was lost")


async def defer_retry_after(
    session: AsyncSession,
    *,
    idempotency_key: str,
    prepared: TelegramDeliveryLease,
    retry_after_seconds: int | None,
    retry_claim_ttl_seconds: int,
    attempts_repo: Any,
) -> TelegramDeliveryOutcome:
    retry_after = max(1, int(retry_after_seconds or 1))
    update_kwargs = cast(dict[str, object], lease_update_kwargs(prepared, attempts_repo))
    if lease_cas_enabled(attempts_repo):
        update_kwargs.update(
            retry_failure_code=RETRY_NEEDED_FAILURE_CODE,
            retry_failure_reason=f"telegram retry needed after {retry_after}s",
        )
    updated = await attempts_repo.defer_retry_after(
        session,
        idempotency_key=idempotency_key,
        retry_after_seconds=retry_after,
        claim_ttl_seconds=retry_claim_ttl_seconds,
        **update_kwargs,
    )
    require_lease_update(updated=updated, status="retry", attempts_repo=attempts_repo)
    return TelegramDeliveryOutcome(
        status="RETRY",
        created=prepared.created,
        attempted=True,
        replayed=prepared.replayed,
        retry_after_seconds=retry_after,
    )
