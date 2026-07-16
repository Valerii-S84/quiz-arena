from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

from app.db.repo.production_reliability_types import (
    TelegramDeliveryAttemptCreate,
    TelegramDeliveryFailure,
)
from app.services.telegram_delivery import (
    TelegramDeliverySkip,
    claim_telegram_delivery_retries,
    deliver_telegram_once,
)
from tests.type_helpers import AsyncSessionStub


class _AttemptsRepo:
    def __init__(self, *, row: object, created: bool) -> None:
        self.row = row
        self.created = created
        self.sent: list[str] = []
        self.failed: list[TelegramDeliveryFailure] = []
        self.skipped: list[tuple[str, str | None]] = []
        self.deferred: list[tuple[str, int, int]] = []

    async def create_once(self, _session, *, attempt):
        return self.row, self.created

    async def mark_sent(self, _session, *, idempotency_key: str) -> bool:
        self.sent.append(idempotency_key)
        return True

    async def mark_failed(self, _session, *, idempotency_key: str, failure) -> bool:
        self.failed.append(failure)
        return True

    async def mark_skipped(
        self,
        _session,
        *,
        idempotency_key: str,
        failure_code: str,
        failure_reason: str | None = None,
    ) -> bool:
        self.skipped.append((failure_code, failure_reason))
        return True

    async def defer_retry_after(
        self,
        _session,
        *,
        idempotency_key: str,
        retry_after_seconds: int,
        claim_ttl_seconds: int,
    ) -> bool:
        self.deferred.append((idempotency_key, retry_after_seconds, claim_ttl_seconds))
        return True


class _RetryRepo:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, int, int]] = []

    async def claim_pending_batch(
        self,
        _session,
        *,
        flow: str,
        limit: int,
        claim_ttl_seconds: int,
    ) -> list[object]:
        self.calls.append((flow, limit, claim_ttl_seconds))
        return self.rows


def _attempt() -> TelegramDeliveryAttemptCreate:
    return TelegramDeliveryAttemptCreate(
        flow="daily_cup",
        task_name="daily_cup.round_delivery",
        correlation_id="round:1",
        idempotency_key="delivery:daily:1:101",
        target_type="daily_cup_round",
        target_id="1",
        telegram_user_id=101,
        safe_context={"round": 1},
    )


@pytest.mark.asyncio
async def test_deliver_telegram_once_preserves_sent_replay_behind_skip_gate() -> None:
    repo = _AttemptsRepo(row=SimpleNamespace(status="SENT"), created=False)

    async def _send() -> object:
        pytest.fail("sent replay must not send again")

    outcome = await deliver_telegram_once(
        AsyncSessionStub(),
        attempt=_attempt(),
        send=_send,
        skip=TelegramDeliverySkip(
            failure_code="BLOCKED_GATE",
            failure_reason="blocked by previous signal",
        ),
        attempts_repo=repo,
    )

    assert outcome.status == "SENT"
    assert outcome.replayed is True
    assert outcome.attempted is False
    assert repo.sent == []
    assert repo.failed == []
    assert repo.skipped == []
    assert repo.deferred == []


@pytest.mark.asyncio
async def test_deliver_telegram_once_blocks_pending_replay_without_sending() -> None:
    repo = _AttemptsRepo(row=SimpleNamespace(status="PENDING"), created=False)

    async def _send() -> object:
        pytest.fail("pending replay must not send concurrently")

    outcome = await deliver_telegram_once(
        AsyncSessionStub(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    assert outcome.status == "RETRY"
    assert outcome.failure_code == "PENDING_REPLAY"
    assert outcome.replayed is True
    assert outcome.attempted is False
    assert repo.sent == []
    assert repo.failed == []
    assert repo.skipped == []
    assert repo.deferred == []


@pytest.mark.asyncio
async def test_deliver_telegram_once_preserves_terminal_failure_metadata() -> None:
    repo = _AttemptsRepo(
        row=SimpleNamespace(
            status="FAILED",
            failure_code="TELEGRAM_FORBIDDEN",
            failure_reason="blocked",
            telegram_error_code=403,
        ),
        created=False,
    )

    async def _send() -> object:
        pytest.fail("terminal replay must not send again")

    outcome = await deliver_telegram_once(
        AsyncSessionStub(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    assert outcome.status == "FAILED"
    assert outcome.failure_code == "TELEGRAM_FORBIDDEN"
    assert outcome.failure_reason == "blocked"
    assert outcome.telegram_error_code == 403
    assert outcome.replayed is True
    assert outcome.attempted is False


@pytest.mark.asyncio
async def test_deliver_telegram_once_marks_pending_skip_without_sending() -> None:
    repo = _AttemptsRepo(row=SimpleNamespace(status="PENDING"), created=True)

    async def _send() -> object:
        pytest.fail("skipped delivery must not call Telegram")

    outcome = await deliver_telegram_once(
        AsyncSessionStub(),
        attempt=_attempt(),
        send=_send,
        skip=TelegramDeliverySkip(failure_code="NO_CHAT_ID", failure_reason="missing target"),
        attempts_repo=repo,
    )

    assert outcome.status == "SKIPPED"
    assert outcome.created is True
    assert outcome.attempted is False
    assert repo.skipped == [("NO_CHAT_ID", "missing target")]
    assert repo.sent == []
    assert repo.failed == []


@pytest.mark.asyncio
async def test_deliver_telegram_once_marks_sent_after_successful_send() -> None:
    repo = _AttemptsRepo(row=SimpleNamespace(status="PENDING"), created=True)
    sends = 0

    async def _send() -> object:
        nonlocal sends
        sends += 1
        return object()

    outcome = await deliver_telegram_once(
        AsyncSessionStub(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    assert outcome.status == "SENT"
    assert outcome.attempted is True
    assert sends == 1
    assert repo.sent == ["delivery:daily:1:101"]
    assert repo.failed == []
    assert repo.skipped == []


@pytest.mark.asyncio
async def test_deliver_telegram_once_records_forbidden_as_blocked_failure() -> None:
    repo = _AttemptsRepo(row=SimpleNamespace(status="PENDING"), created=True)

    async def _send() -> object:
        raise TelegramForbiddenError(
            method=SendMessage(chat_id=101, text="x"),
            message="bot was blocked by the user",
        )

    outcome = await deliver_telegram_once(
        AsyncSessionStub(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    assert outcome.status == "FAILED"
    assert outcome.failure_code == "TELEGRAM_FORBIDDEN"
    assert outcome.telegram_error_code == 403
    assert repo.sent == []
    assert repo.skipped == []
    assert len(repo.failed) == 1
    failure = repo.failed[0]
    assert failure.is_blocked_candidate is True
    assert failure.telegram_error_code == 403


@pytest.mark.asyncio
async def test_deliver_telegram_once_keeps_retry_after_pending_for_retry() -> None:
    repo = _AttemptsRepo(row=SimpleNamespace(status="PENDING"), created=True)

    async def _send() -> object:
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=101, text="x"),
            message="flood",
            retry_after=7,
        )

    outcome = await deliver_telegram_once(
        AsyncSessionStub(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    assert outcome.status == "RETRY"
    assert outcome.retry_after_seconds == 7
    assert outcome.attempted is True
    assert outcome.replayed is False
    assert repo.sent == []
    assert repo.failed == []
    assert repo.skipped == []
    assert repo.deferred == [("delivery:daily:1:101", 7, 300)]


@pytest.mark.asyncio
async def test_deliver_telegram_once_reraises_unclassified_failures() -> None:
    repo = _AttemptsRepo(row=SimpleNamespace(status="PENDING"), created=True)

    async def _send() -> object:
        raise RuntimeError("ambiguous send failure")

    with pytest.raises(RuntimeError, match="ambiguous send failure"):
        await deliver_telegram_once(
            AsyncSessionStub(),
            attempt=_attempt(),
            send=_send,
            attempts_repo=repo,
        )

    assert repo.sent == []
    assert repo.failed == []
    assert repo.skipped == []


@pytest.mark.asyncio
async def test_claim_telegram_delivery_retries_delegates_pending_claim() -> None:
    rows: list[object] = [SimpleNamespace(id=1)]
    repo = _RetryRepo(rows)

    assert (
        await claim_telegram_delivery_retries(
            AsyncSessionStub(),
            flow="daily_cup",
            limit=25,
            claim_ttl_seconds=120,
            retry_repo=repo,
        )
        == rows
    )
    assert repo.calls == [("daily_cup", 25, 120)]
