from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendMessage

from app.db.repo.production_reliability_types import (
    TelegramDeliveryAttemptCreate,
    TelegramDeliveryFailure,
)
from app.services.telegram_blocked_candidate_policy import (
    BLOCKED_CANDIDATE_FAILURE_CODE,
    BLOCKED_CANDIDATE_TTL,
)
from app.services.telegram_delivery import deliver_telegram_once
from tests.type_helpers import AsyncBeginContext


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


class _PolicyRepo:
    def __init__(self, *, blocked: bool = False, status: str = "PENDING") -> None:
        self.blocked = blocked
        self.row = SimpleNamespace(status=status)
        self.blocked_since: datetime | None = None
        self.skipped: list[tuple[str, str | None]] = []
        self.failed: list[TelegramDeliveryFailure] = []
        self.sent = 0

    async def create_once(self, _session, *, attempt):
        return self.row, True

    async def has_blocked_candidate(
        self, _session, *, telegram_user_id: int, blocked_since: datetime
    ) -> bool:
        assert telegram_user_id == 101
        self.blocked_since = blocked_since
        return self.blocked

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

    async def mark_failed(
        self, _session, *, idempotency_key: str, failure: TelegramDeliveryFailure
    ) -> bool:
        self.failed.append(failure)
        return True

    async def mark_sent(self, _session, *, idempotency_key: str) -> bool:
        self.sent += 1
        return True


def _attempt() -> TelegramDeliveryAttemptCreate:
    return TelegramDeliveryAttemptCreate(
        flow="registration_push",
        task_name="registration_push",
        correlation_id="push:1",
        idempotency_key="telegram:push:1",
        target_type="user",
        target_id="1",
        telegram_user_id=101,
    )


async def test_known_blocked_candidate_is_persisted_as_skipped_without_send() -> None:
    repo = _PolicyRepo(blocked=True)
    sends = 0
    earliest = datetime.now(UTC) - BLOCKED_CANDIDATE_TTL - timedelta(seconds=1)

    async def _send() -> object:
        nonlocal sends
        sends += 1
        return object()

    outcome = await deliver_telegram_once(
        _SessionLocal(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    latest = datetime.now(UTC) - BLOCKED_CANDIDATE_TTL + timedelta(seconds=1)
    assert outcome.status == "SKIPPED"
    assert outcome.failure_code == BLOCKED_CANDIDATE_FAILURE_CODE
    assert sends == 0
    assert repo.blocked_since is not None
    assert earliest <= repo.blocked_since <= latest
    assert repo.skipped == [(BLOCKED_CANDIDATE_FAILURE_CODE, "known blocked candidate")]


@pytest.mark.parametrize(
    ("exc", "failure_code", "blocked"),
    [
        (
            TelegramBadRequest(
                method=SendMessage(chat_id=101, text="x"),
                message="chat not found: private detail",
            ),
            "TELEGRAM_BAD_REQUEST",
            True,
        ),
        (
            TelegramNetworkError(
                method=SendMessage(chat_id=101, text="x"),
                message="connection reset: private detail",
            ),
            "TELEGRAM_TRANSIENT_SEND_ERROR",
            False,
        ),
    ],
)
async def test_classified_failure_is_persisted_with_safe_reason(
    exc: Exception, failure_code: str, blocked: bool
) -> None:
    repo = _PolicyRepo()

    async def _send() -> object:
        raise exc

    outcome = await deliver_telegram_once(
        _SessionLocal(),
        attempt=_attempt(),
        send=_send,
        attempts_repo=repo,
    )

    assert outcome.status == "FAILED"
    assert outcome.failure_code == failure_code
    assert len(repo.failed) == 1
    failure = repo.failed[0]
    assert failure.failure_code == failure_code
    assert failure.failure_reason == type(exc).__name__
    assert failure.is_blocked_candidate is blocked
