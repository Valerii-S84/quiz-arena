from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.db.repo.telegram_delivery_retry_repo import (
    PENDING_REPLAY_SAFE_CONTEXT_KEY,
    RETRY_NEEDED_FAILURE_CODE,
)
from app.services.telegram_delivery import deliver_telegram_once
from tests.type_helpers import AsyncSessionStub


class _SessionBegin:
    async def __aenter__(self) -> AsyncSessionStub:
        return AsyncSessionStub()

    async def __aexit__(self, *_args: object) -> None:
        return None


class _SessionLocal:
    @staticmethod
    def begin() -> _SessionBegin:
        return _SessionBegin()


class _LeaseRepo:
    supports_delivery_lease_cas = True

    def __init__(
        self,
        *,
        row: SimpleNamespace,
        created: bool,
        dispatch_succeeds: bool = True,
        terminal_update_succeeds: bool = True,
    ) -> None:
        self.row = row
        self.created = created
        self.dispatch_succeeds = dispatch_succeeds
        self.terminal_update_succeeds = terminal_update_succeeds
        self.stale_claims: list[int] = []
        self.dispatch_claims: list[int] = []
        self.sent_leases: list[int] = []
        self.deferred: list[dict[str, object]] = []

    async def create_once(self, _session: object, *, attempt: object) -> tuple[object, bool]:
        return self.row, self.created

    async def claim_stale_pending_replay(
        self,
        _session: object,
        *,
        idempotency_key: str,
        claim_ttl_seconds: int,
    ) -> int:
        self.row.attempt_count += 1
        self.stale_claims.append(self.row.attempt_count)
        return int(self.row.attempt_count)

    async def claim_pending_replay_dispatch(
        self,
        _session: object,
        *,
        idempotency_key: str,
        expected_attempt_count: int,
    ) -> int | None:
        self.dispatch_claims.append(expected_attempt_count)
        if not self.dispatch_succeeds or self.row.attempt_count != expected_attempt_count:
            return None
        self.row.attempt_count += 1
        self.row.failure_code = None
        return int(self.row.attempt_count)

    async def mark_sent(
        self,
        _session: object,
        *,
        idempotency_key: str,
        expected_attempt_count: int,
    ) -> bool:
        self.sent_leases.append(expected_attempt_count)
        return self.terminal_update_succeeds

    async def mark_failed(self, _session: object, **kwargs: object) -> bool:
        return self.terminal_update_succeeds

    async def mark_skipped(self, _session: object, **kwargs: object) -> bool:
        return self.terminal_update_succeeds

    async def defer_retry_after(self, _session: object, **kwargs: object) -> bool:
        self.deferred.append(kwargs)
        return self.terminal_update_succeeds


def _attempt() -> TelegramDeliveryAttemptCreate:
    return TelegramDeliveryAttemptCreate(
        flow="telegram_delivery",
        task_name="telegram_delivery.retry",
        correlation_id="retry:1",
        idempotency_key="telegram:retry:1",
        target_type="telegram_message",
        target_id="1",
    )


def _pending_row(
    *,
    attempt_count: int,
    replay_safe: bool = False,
    failure_code: str | None = None,
) -> SimpleNamespace:
    safe_context: dict[str, Any] = {}
    if replay_safe:
        safe_context[PENDING_REPLAY_SAFE_CONTEXT_KEY] = True
    return SimpleNamespace(
        status="PENDING",
        attempt_count=attempt_count,
        safe_context=safe_context,
        failure_code=failure_code,
    )


@pytest.mark.asyncio
async def test_unsafe_pending_replay_stays_closed_without_claim_or_send() -> None:
    repo = _LeaseRepo(row=_pending_row(attempt_count=2), created=False)
    sends = 0

    async def _send() -> object:
        nonlocal sends
        sends += 1
        return object()

    outcome = await deliver_telegram_once(
        _SessionLocal(),
        attempt=_attempt(),
        send=_send,
        allow_stale_pending_replay_send=True,
        attempts_repo=repo,
    )

    assert outcome.status == "RETRY"
    assert sends == 0
    assert repo.stale_claims == []
    assert repo.dispatch_claims == []


@pytest.mark.asyncio
async def test_guaranteed_undelivered_retry_claims_and_sends_once() -> None:
    repo = _LeaseRepo(
        row=_pending_row(attempt_count=2, failure_code=RETRY_NEEDED_FAILURE_CODE),
        created=False,
    )
    sends = 0

    async def _send() -> object:
        nonlocal sends
        sends += 1
        return object()

    outcome = await deliver_telegram_once(
        _SessionLocal(),
        attempt=_attempt(),
        send=_send,
        allow_stale_pending_replay_send=True,
        attempts_repo=repo,
    )

    assert outcome.status == "SENT"
    assert sends == 1
    assert repo.stale_claims == [3]
    assert repo.dispatch_claims == [3]
    assert repo.sent_leases == [4]


@pytest.mark.asyncio
async def test_preselected_retry_dispatch_uses_exact_claim_token() -> None:
    repo = _LeaseRepo(row=_pending_row(attempt_count=5, replay_safe=True), created=False)

    async def _send() -> object:
        return object()

    outcome = await deliver_telegram_once(
        _SessionLocal(),
        attempt=_attempt(),
        send=_send,
        allow_pending_replay_send=True,
        pending_replay_claim_attempt_count=5,
        attempts_repo=repo,
    )

    assert outcome.status == "SENT"
    assert repo.dispatch_claims == [5]
    assert repo.sent_leases == [6]


@pytest.mark.asyncio
async def test_lost_retry_dispatch_lease_blocks_send() -> None:
    repo = _LeaseRepo(
        row=_pending_row(attempt_count=5, replay_safe=True),
        created=False,
        dispatch_succeeds=False,
    )
    sends = 0

    async def _send() -> object:
        nonlocal sends
        sends += 1
        return object()

    with pytest.raises(RuntimeError, match="retry lease was lost"):
        await deliver_telegram_once(
            _SessionLocal(),
            attempt=_attempt(),
            send=_send,
            allow_pending_replay_send=True,
            pending_replay_claim_attempt_count=5,
            attempts_repo=repo,
        )

    assert sends == 0


@pytest.mark.asyncio
async def test_lost_terminal_lease_does_not_report_sent() -> None:
    repo = _LeaseRepo(
        row=_pending_row(attempt_count=1),
        created=True,
        terminal_update_succeeds=False,
    )

    async def _send() -> object:
        return object()

    with pytest.raises(RuntimeError, match="sent lease was lost"):
        await deliver_telegram_once(
            _SessionLocal(),
            attempt=_attempt(),
            send=_send,
            attempts_repo=repo,
        )

    assert repo.sent_leases == [1]


@pytest.mark.asyncio
async def test_retry_after_persists_guaranteed_undelivered_marker_with_lease() -> None:
    repo = _LeaseRepo(row=_pending_row(attempt_count=1), created=True)

    async def _send() -> object:
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=1, text="x"),
            message="flood",
            retry_after=7,
        )

    outcome = await deliver_telegram_once(
        _SessionLocal(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    assert outcome.status == "RETRY"
    assert repo.deferred == [
        {
            "idempotency_key": "telegram:retry:1",
            "retry_after_seconds": 7,
            "claim_ttl_seconds": 300,
            "expected_attempt_count": 1,
            "retry_failure_code": RETRY_NEEDED_FAILURE_CODE,
            "retry_failure_reason": "telegram retry needed after 7s",
        }
    ]
