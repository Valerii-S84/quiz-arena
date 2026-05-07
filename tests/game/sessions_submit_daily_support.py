from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.service import sessions_submit_daily
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc

NOW_UTC = datetime(2026, 4, 24, 8, 0, tzinfo=UTC)

BERLIN_DATE = date(2026, 4, 24)


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


__all__ = [
    "AsyncSessionStub",
    "BERLIN_DATE",
    "NOW_UTC",
    "QuizSession",
    "SimpleNamespace",
    "UTC",
    "UUID",
    "_Session",
    "_async_return",
    "cast",
    "date",
    "datetime",
    "pytest",
    "sessions_submit_daily",
    "timezone",
    "uuid4",
]
