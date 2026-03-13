from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import users_helpers
from app.db.models.energy_state import EnergyState
from app.db.models.streak_state import StreakState
from app.main import app


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ScalarsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(
        self, *, gets: dict[tuple[str, int], object] | None = None, exec_results=None
    ) -> None:
        self.gets = gets or {}
        self.exec_results = list(exec_results or [])
        self.added: list[object] = []
        self.flushed = False

    async def get(self, model, key):
        return self.gets.get((model.__name__, key))

    async def execute(self, stmt):
        del stmt
        return self.exec_results.pop(0)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed = True


class _AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _session_local(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)
    return SimpleNamespace(begin=lambda: _AsyncBeginContext(remaining.pop(0)))


def _admin() -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[admin_deps.get_current_admin] = _admin
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_build_search_filters_handles_blank_text_and_numeric_search() -> None:
    assert users_helpers._build_search_filters("") == []
    assert len(users_helpers._build_search_filters("anna")) == 1
    assert len(users_helpers._build_search_filters("123")) == 1


@pytest.mark.asyncio
async def test_list_users_page_builds_rows_and_total() -> None:
    user_rows = [
        SimpleNamespace(
            id=101,
            telegram_user_id=900101,
            username="anna",
            first_name="Anna",
            language_code="de",
            status="ACTIVE",
            created_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
            last_seen_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=202,
            telegram_user_id=900202,
            username="bert",
            first_name="Bert",
            language_code="en",
            status="BLOCKED",
            created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            last_seen_at=None,
        ),
    ]
    session = _Session(
        exec_results=[
            _ScalarResult(2),
            _ScalarsResult(user_rows),
            _RowsResult([(101, 5)]),
        ]
    )

    rows, total = await users_helpers.list_users_page(
        session,
        search="anna",
        language="de",
        level="A2",
        page=1,
        limit=50,
    )

    assert total == 2
    assert rows[0]["telegram_user_id"] == 900101
    assert rows[0]["streak"] == 5
    assert rows[1]["streak"] == 0


@pytest.mark.asyncio
async def test_list_users_page_returns_empty_result_without_filters() -> None:
    session = _Session(exec_results=[_ScalarResult(0), _ScalarsResult([]), _RowsResult([])])

    rows, total = await users_helpers.list_users_page(
        session,
        search="   ",
        language=None,
        level=None,
        page=2,
        limit=25,
    )

    assert rows == []
    assert total == 0


@pytest.mark.asyncio
async def test_get_user_profile_builds_sections_and_timeline() -> None:
    user = SimpleNamespace(
        id=101,
        telegram_user_id=900101,
        username="anna",
        first_name="Anna",
        language_code="de",
        status="ACTIVE",
        created_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
    )
    streak = SimpleNamespace(current_streak=5, best_streak=7)
    energy = SimpleNamespace(paid_energy=12)
    purchase = SimpleNamespace(
        id=uuid4(),
        product_code="premium",
        stars_amount=500,
        status="CREDITED",
        paid_at=datetime(2026, 3, 5, 10, 0, tzinfo=UTC),
    )
    referral = SimpleNamespace(
        id=1,
        referrer_user_id=101,
        referred_user_id=202,
        status="COMPLETED",
        created_at=datetime(2026, 3, 4, 10, 0, tzinfo=UTC),
    )
    session = _Session(
        gets={
            ("User", 101): user,
            ("StreakState", 101): streak,
            ("EnergyState", 101): energy,
        },
        exec_results=[
            _RowsResult([("QUIZ", "A2")]),
            _ScalarsResult([purchase]),
            _ScalarsResult([referral]),
            _RowsResult([("quiz_finished", datetime(2026, 3, 6, 10, 0, tzinfo=UTC), {"q": 1})]),
            _RowsResult(
                [("admin_bonus_energy", datetime(2026, 3, 7, 10, 0, tzinfo=UTC), {"amount": 3})]
            ),
        ],
    )

    profile = await users_helpers.get_user_profile(session, 101)

    assert profile["info"]["telegram_user_id"] == 900101
    assert profile["progress"]["levels"] == [{"mode": "QUIZ", "level": "A2"}]
    assert profile["purchases"][0]["product"] == "premium"
    assert profile["referrals"][0]["referrer_user_id"] == 101
    assert profile["timeline"][0]["type"] == "admin_bonus_energy"


@pytest.mark.asyncio
async def test_get_user_profile_defaults_related_sections_and_missing_user() -> None:
    with pytest.raises(HTTPException) as missing_user:
        await users_helpers.get_user_profile(_Session(gets={}), 404)
    assert missing_user.value.status_code == 404

    user = SimpleNamespace(
        id=202,
        telegram_user_id=900202,
        username="bert",
        first_name="Bert",
        language_code="en",
        status="ACTIVE",
        created_at=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
        last_seen_at=None,
    )
    purchase = SimpleNamespace(
        id=uuid4(),
        product_code="energy_pack",
        stars_amount=150,
        status="PENDING",
        paid_at=None,
    )
    session = _Session(
        gets={("User", 202): user, ("StreakState", 202): None, ("EnergyState", 202): None},
        exec_results=[
            _RowsResult([]),
            _ScalarsResult([purchase]),
            _ScalarsResult([]),
            _RowsResult([]),
            _RowsResult([]),
        ],
    )

    profile = await users_helpers.get_user_profile(session, 202)

    assert profile["info"]["last_seen_at"] is None
    assert profile["progress"] == {"levels": [], "streak": 0, "best_streak": 0, "paid_energy": 0}
    assert profile["purchases"][0]["paid_at"] is None
    assert profile["referrals"] == []
    assert profile["timeline"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bonus_type", "amount"),
    [("energy", 3), ("streak_token", 2), ("premium_days", 7)],
)
async def test_apply_bonus_handles_supported_bonus_types(
    monkeypatch: pytest.MonkeyPatch,
    bonus_type: str,
    amount: int,
) -> None:
    class _FrozenDatetime:
        @staticmethod
        def now(tz):
            return datetime(2026, 3, 10, 12, 0, tzinfo=tz)

    monkeypatch.setattr(users_helpers, "datetime", _FrozenDatetime)
    user = SimpleNamespace(id=101)
    gets = {("User", 101): user}
    if bonus_type == "energy":
        gets[("EnergyState", 101)] = None
    elif bonus_type == "streak_token":
        gets[("StreakState", 101)] = None
    session = _Session(gets=gets)

    result = await users_helpers.apply_bonus(
        session, user_id=101, bonus_type=bonus_type, amount=amount
    )

    assert result == {"user_id": 101, "bonus_type": bonus_type, "amount": amount}
    assert session.flushed is True
    assert any(type(item).__name__ == "UserEvent" for item in session.added)
    if bonus_type == "energy":
        assert any(isinstance(item, EnergyState) for item in session.added)
    elif bonus_type == "streak_token":
        assert any(isinstance(item, StreakState) for item in session.added)
    else:
        assert any(type(item).__name__ == "Entitlement" for item in session.added)


@pytest.mark.asyncio
async def test_apply_bonus_rejects_invalid_bonus_type_and_missing_user() -> None:
    with pytest.raises(HTTPException) as missing_user:
        await users_helpers.apply_bonus(
            _Session(gets={}), user_id=101, bonus_type="energy", amount=1
        )
    assert missing_user.value.status_code == 404

    with pytest.raises(HTTPException) as invalid_bonus:
        await users_helpers.apply_bonus(
            _Session(gets={("User", 101): SimpleNamespace(id=101)}),
            user_id=101,
            bonus_type="unknown",
            amount=1,
        )
    assert invalid_bonus.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bonus_type", "field_name"),
    [("energy", "paid_energy"), ("streak_token", "streak_saver_tokens")],
)
async def test_apply_bonus_updates_existing_state_without_creating_duplicate_record(
    monkeypatch: pytest.MonkeyPatch,
    bonus_type: str,
    field_name: str,
) -> None:
    class _FrozenDatetime:
        @staticmethod
        def now(tz):
            return datetime(2026, 3, 10, 12, 0, tzinfo=tz)

    monkeypatch.setattr(users_helpers, "datetime", _FrozenDatetime)
    existing_state = SimpleNamespace(updated_at=None, **{field_name: 4})
    gets = {("User", 101): SimpleNamespace(id=101)}
    if bonus_type == "energy":
        gets[("EnergyState", 101)] = existing_state
    else:
        gets[("StreakState", 101)] = existing_state
    session = _Session(gets=gets)

    result = await users_helpers.apply_bonus(session, user_id=101, bonus_type=bonus_type, amount=3)

    assert result["amount"] == 3
    assert getattr(existing_state, field_name) == 7
    assert not any(isinstance(item, (EnergyState, StreakState)) for item in session.added)
