from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import content
from app.api.routes.admin import deps as admin_deps
from app.main import app


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def all_scalars(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _ScalarsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _ScalarOneOrNoneResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Session:
    def __init__(self, *, exec_results=None, gets=None) -> None:
        self.exec_results = list(exec_results or [])
        self.gets = gets or {}

    async def execute(self, stmt):
        del stmt
        return self.exec_results.pop(0)

    async def get(self, model, key):
        return self.gets.get((model.__name__, key))


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


def test_admin_content_health_returns_aggregated_payload(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    flagged = SimpleNamespace(
        id=1,
        user_id=101,
        event_type="question_flagged",
        payload={"question_id": "q1"},
        created_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
    )
    grammar_event = SimpleNamespace(
        payload={"status": "ok"},
        created_at=datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
    )
    session = _Session(
        exec_results=[
            _RowsResult([("A1", 10), ("B1", 5)]),
            _RowsResult([("A1", 4), ("B1", 5)]),
            _ScalarsResult([flagged]),
            _ScalarOneOrNoneResult(grammar_event),
            _RowsResult([("Hallo?", 2)]),
            _RowsResult([("QUIZ", "A1", 4), ("QUIZ", "B1", 2)]),
        ]
    )
    monkeypatch.setattr(content, "SessionLocal", _session_local(session))

    response = client.get("/admin/content")

    assert response.status_code == 200
    payload = response.json()
    assert payload["level_stats"][0]["coverage_percent"] == 40.0
    assert payload["flagged_questions"][0]["reason"] == "question_flagged"
    assert payload["grammar_pipeline"]["status"] == "ok"
    assert payload["duplicates"] == [{"question_text": "Hallo?", "count": 2}]
    assert payload["mode_level_distribution"][0]["percent_in_mode"] == 66.67


def test_admin_content_helpers_and_empty_branches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert content._level_sort_key("b2") == (4, "B2")
    assert content._level_sort_key("z9") == (99, "Z9")

    session = _Session(
        exec_results=[
            _RowsResult([("Z9", 0)]),
            _RowsResult([]),
            _ScalarsResult([]),
            _ScalarOneOrNoneResult(None),
            _RowsResult([]),
            _RowsResult([]),
        ]
    )
    monkeypatch.setattr(content, "SessionLocal", _session_local(session))

    response = client.get("/admin/content")

    assert response.status_code == 200
    payload = response.json()
    assert payload["level_stats"] == [
        {"level": "Z9", "total_questions": 0, "attempts": 0, "coverage_percent": 0}
    ]
    assert payload["grammar_pipeline"] == {"status": "unknown", "updated_at": None, "payload": {}}
    assert payload["flagged_questions"] == []
    assert payload["duplicates"] == []
    assert payload["mode_level_distribution"] == []


def test_admin_content_review_routes_update_payload_and_write_audit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    approve_event = SimpleNamespace(id=1, payload={"x": 1})
    reject_event = SimpleNamespace(id=2, payload={"x": 2})
    audit_calls: list[dict[str, object]] = []

    async def _audit(session, **kwargs):
        del session
        audit_calls.append(kwargs)

    monkeypatch.setattr(
        content,
        "SessionLocal",
        _session_local(
            _Session(gets={("UserEvent", 1): approve_event}),
            _Session(gets={("UserEvent", 2): reject_event}),
        ),
    )
    monkeypatch.setattr(content, "write_admin_audit", _audit)

    approve = client.post("/admin/content/flagged/1/approve")
    reject = client.post("/admin/content/flagged/2/reject?reason=spam")

    assert approve.status_code == 200
    assert reject.status_code == 200
    assert approve_event.payload["review"] == "approved"
    assert reject_event.payload["review"] == "rejected"
    assert reject_event.payload["reason"] == "spam"
    assert [call["action"] for call in audit_calls] == [
        "content_flag_approve",
        "content_flag_reject",
    ]


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/admin/content/flagged/404/approve", ""),
        ("/admin/content/flagged/404/reject", "?reason=spam"),
    ],
)
def test_admin_content_review_routes_return_not_found(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    query: str,
) -> None:
    monkeypatch.setattr(
        content, "SessionLocal", _session_local(_Session(gets={("UserEvent", 404): None}))
    )

    response = client.post(f"{path}{query}")

    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "E_FLAG_NOT_FOUND"}}
