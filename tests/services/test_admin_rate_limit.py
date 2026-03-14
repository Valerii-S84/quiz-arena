from __future__ import annotations

from collections import deque

import pytest

from app.services.admin import rate_limit


@pytest.fixture(autouse=True)
def _reset_rate_limit_state() -> None:
    rate_limit._FAILED_ATTEMPTS.clear()


def test_is_rate_limited_returns_false_for_unknown_bucket() -> None:
    assert rate_limit.is_rate_limited(bucket="missing", limit=3, window_seconds=60) is False


def test_is_rate_limited_returns_false_below_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    rate_limit._FAILED_ATTEMPTS["bucket"] = deque([100.0])
    monkeypatch.setattr(rate_limit, "monotonic", lambda: 100.5)

    assert rate_limit.is_rate_limited(bucket="bucket", limit=2, window_seconds=60) is False


def test_record_failure_and_is_rate_limited_clamp_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([100.0, 100.0])
    monkeypatch.setattr(rate_limit, "monotonic", lambda: next(times))

    rate_limit.record_failure(bucket="bucket", window_seconds=0)

    assert rate_limit.is_rate_limited(bucket="bucket", limit=0, window_seconds=0) is True


def test_is_rate_limited_discards_expired_attempts_and_prunes_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limit._FAILED_ATTEMPTS["bucket"] = deque([10.0])
    monkeypatch.setattr(rate_limit, "monotonic", lambda: 12.1)

    assert rate_limit.is_rate_limited(bucket="bucket", limit=1, window_seconds=1) is False
    assert "bucket" not in rate_limit._FAILED_ATTEMPTS


def test_record_failure_discards_expired_attempts_before_appending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limit._FAILED_ATTEMPTS["bucket"] = deque([10.0])
    monkeypatch.setattr(rate_limit, "monotonic", lambda: 12.1)

    rate_limit.record_failure(bucket="bucket", window_seconds=1)

    assert list(rate_limit._FAILED_ATTEMPTS["bucket"]) == [12.1]


def test_clear_failures_removes_existing_bucket_and_ignores_missing() -> None:
    rate_limit._FAILED_ATTEMPTS["bucket"] = deque([1.0])

    rate_limit.clear_failures(bucket="bucket")
    rate_limit.clear_failures(bucket="missing")

    assert rate_limit._FAILED_ATTEMPTS == {}
