from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.economy.referrals.service.rewards_claim as rewards_claim
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


class _Session(AsyncSessionStub):
    pass


def _overview(status: str) -> SimpleNamespace:
    return SimpleNamespace(status=status)


def _anchor(
    *,
    referral_id: int,
    status: str = "QUALIFIED",
    qualified_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=referral_id,
        status=status,
        qualified_at=qualified_at,
        rewarded_at=None,
    )


__all__ = [
    "AsyncSessionStub",
    "SimpleNamespace",
    "UTC",
    "_Session",
    "_anchor",
    "_overview",
    "datetime",
    "pytest",
    "rewards_claim",
    "timedelta",
    "timezone",
]
