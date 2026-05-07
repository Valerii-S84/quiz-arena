from __future__ import annotations

import pytest

from app.game.sessions.service import progression_recent_results
from tests.type_helpers import AsyncSessionStub, ScalarsResult


class _Session(AsyncSessionStub):
    def __init__(self) -> None:
        self.stmt = None

    async def execute(self, stmt):
        self.stmt = stmt
        return ScalarsResult([1, 0, True, False])


@pytest.mark.asyncio
async def test_recent_attempt_results_returns_bool_list_and_executes_query() -> None:
    session = _Session()

    result = await progression_recent_results.recent_attempt_results(
        session,
        user_id=11,
        mode="QUICK_MIX_A1A2",
        limit=4,
    )

    assert result == [True, False, True, False]
    assert session.stmt is not None
