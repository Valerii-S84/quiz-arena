from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.routes.admin.pagination import build_pagination
from app.api.routes.admin.users_listing import _build_search_filters, list_users_page
from tests.type_helpers import AsyncSessionStub
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult


class _Session(AsyncSessionStub):
    def __init__(self, *results: object) -> None:
        self.results = list(results)

    async def execute(self, stmt):
        del stmt
        return self.results.pop(0)


def test_build_search_filters_ignores_blank_and_adds_numeric_matches() -> None:
    assert _build_search_filters("  ") == []
    assert len(_build_search_filters("anna")) == 1
    assert len(_build_search_filters("900101")) == 1


def test_build_pagination_clamps_empty_and_out_of_range_inputs() -> None:
    assert build_pagination(total=-3, page=0, limit=999) == {
        "total": 0,
        "page": 1,
        "pages": 1,
        "limit": 200,
    }
    assert build_pagination(total=201, page=2, limit=100)["pages"] == 3


@pytest.mark.asyncio
async def test_list_users_page_defaults_missing_scores_and_streaks() -> None:
    user = SimpleNamespace(
        id=101,
        telegram_user_id=900101,
        username=None,
        first_name="Anna",
        language_code="de",
        status="ACTIVE",
        created_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        last_seen_at=None,
    )
    session = _Session(_ScalarResult(1), _RowsResult([(user, None, None)]), _RowsResult([]))

    rows, total = await list_users_page(
        session,
        search="",
        language=None,
        level=None,
        page=3,
        limit=25,
    )

    assert total == 1
    assert rows == [
        {
            "id": 101,
            "telegram_user_id": 900101,
            "username": None,
            "first_name": "Anna",
            "language": "de",
            "status": "ACTIVE",
            "created_at": "2026-03-01T10:00:00+00:00",
            "last_seen_at": None,
            "streak": 0,
            "daily_challenge_score": 0,
            "daily_challenge_completed_runs": 0,
        }
    ]
