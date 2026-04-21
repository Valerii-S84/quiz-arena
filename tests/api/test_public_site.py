from fastapi.testclient import TestClient

from app.api.routes import public_contact as public_contact_routes
from app.api.routes import public_site as public_site_routes
from app.main import app


async def _metrics_stub() -> dict[str, object]:
    return {
        "users_total": 1234,
        "quizzes_total": 5678,
        "purchases_total": 0,
        "revenue_stars_total": 0,
        "revenue_eur_total": 0.0,
    }


class _SessionLocalStub:
    def __init__(self) -> None:
        self.added_rows: list[object] = []

    def begin(self):
        return _SessionContextStub(self)

    def add(self, item: object) -> None:
        self.added_rows.append(item)


class _SessionContextStub:
    def __init__(self, session: _SessionLocalStub) -> None:
        self._session = session

    async def __aenter__(self) -> _SessionLocalStub:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _RedisRateLimitStub:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)


def _install_contact_rate_limit_stub(
    monkeypatch,
    redis_stub: _RedisRateLimitStub | None = None,
) -> _RedisRateLimitStub | None:
    async def _client(_settings):
        return redis_stub

    monkeypatch.setattr(public_contact_routes, "get_redis_client", _client)
    return redis_stub


def test_api_stats_maps_public_metrics(monkeypatch) -> None:
    monkeypatch.setattr(public_site_routes, "_collect_public_metrics", _metrics_stub)

    client = TestClient(app)
    response = client.get("/api/stats")

    assert response.status_code == 200
    assert response.json() == {"users": 1234, "quizzes": 5678}


def test_stats_alias_maps_public_metrics(monkeypatch) -> None:
    monkeypatch.setattr(public_site_routes, "_collect_public_metrics", _metrics_stub)

    client = TestClient(app)
    response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {"users": 1234, "quizzes": 5678}


def test_contact_student_request_is_accepted(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, _RedisRateLimitStub())
    client = TestClient(app)

    response = client.post(
        "/api/contact",
        json={
            "type": "student",
            "name": "Max",
            "contact": "@max",
            "ageGroup": "16-25",
            "level": "A2",
            "goals": ["Alltagssprache"],
            "format": "Individuell mit Lehrkraft",
            "timeSlots": ["Abend"],
            "frequency": "2x pro Woche",
            "budget": "50-100",
            "message": "Hallo",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert len(session_stub.added_rows) == 1


def test_contact_alias_student_request_is_accepted(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, _RedisRateLimitStub())
    client = TestClient(app)

    response = client.post(
        "/contact",
        json={
            "type": "student",
            "name": "Max",
            "contact": "@max",
            "ageGroup": "16-25",
            "level": "A2",
            "goals": ["Alltagssprache"],
            "format": "Individuell mit Lehrkraft",
            "timeSlots": ["Abend"],
            "frequency": "2x pro Woche",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert len(session_stub.added_rows) == 1


def test_contact_student_requires_goals(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, _RedisRateLimitStub())
    client = TestClient(app)

    response = client.post(
        "/api/contact",
        json={
            "type": "student",
            "name": "Max",
            "contact": "@max",
            "ageGroup": "16-25",
            "level": "A2",
            "format": "Individuell mit Lehrkraft",
            "timeSlots": ["Abend"],
            "frequency": "2x pro Woche",
            "message": "Hallo",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "E_GOALS_REQUIRED"
    assert not session_stub.added_rows


def test_contact_partner_request_is_accepted(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, _RedisRateLimitStub())
    client = TestClient(app)

    response = client.post(
        "/api/contact",
        json={
            "type": "partner",
            "name": "Org",
            "partnerType": "Sprachschule",
            "country": "Deutschland / Berlin",
            "studentCount": "10-50",
            "offerings": ["Unterricht für Quiz Arena Nutzer"],
            "contact": "org@example.com",
            "website": "https://example.com",
            "idea": "Wir wollen gemeinsame Gruppenkurse starten.",
            "startTimeline": "Innerhalb eines Monats",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert len(session_stub.added_rows) == 1


def test_contact_partner_requires_idea(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, _RedisRateLimitStub())
    client = TestClient(app)

    response = client.post(
        "/api/contact",
        json={
            "type": "partner",
            "name": "Org",
            "partnerType": "Sprachschule",
            "country": "Deutschland / Berlin",
            "studentCount": "10-50",
            "offerings": ["Unterricht für Quiz Arena Nutzer"],
            "contact": "org@example.com",
            "startTimeline": "Innerhalb eines Monats",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "E_IDEA_REQUIRED"
    assert not session_stub.added_rows


def test_contact_honeypot_request_is_ignored(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, _RedisRateLimitStub())
    client = TestClient(app)

    response = client.post(
        "/api/contact",
        json={
            "type": "student",
            "name": "Max",
            "company": "Spam Corp",
            "contact": "@max",
            "ageGroup": "16-25",
            "level": "A2",
            "goals": ["Alltagssprache"],
            "format": "Individuell mit Lehrkraft",
            "timeSlots": ["Abend"],
            "frequency": "2x pro Woche",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert session_stub.added_rows == []


def test_contact_request_is_rate_limited_after_three_submissions(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    redis_stub = _RedisRateLimitStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, redis_stub)
    client = TestClient(app)
    payload = {
        "type": "student",
        "name": "Max",
        "contact": "@max",
        "ageGroup": "16-25",
        "level": "A2",
        "goals": ["Alltagssprache"],
        "format": "Individuell mit Lehrkraft",
        "timeSlots": ["Abend"],
        "frequency": "2x pro Woche",
    }

    for _ in range(3):
        response = client.post("/api/contact", json=payload)
        assert response.status_code == 202

    response = client.post("/api/contact", json=payload)

    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "E_RATE_LIMITED"}}
    assert len(session_stub.added_rows) == 3
    assert len(redis_stub.counts) == 1


def test_contact_returns_503_when_rate_limit_store_is_unavailable(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    _install_contact_rate_limit_stub(monkeypatch, None)
    client = TestClient(app)

    response = client.post(
        "/api/contact",
        json={
            "type": "student",
            "name": "Max",
            "contact": "@max",
            "ageGroup": "16-25",
            "level": "A2",
            "goals": ["Alltagssprache"],
            "format": "Individuell mit Lehrkraft",
            "timeSlots": ["Abend"],
            "frequency": "2x pro Woche",
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_CONTACT_TEMPORARILY_UNAVAILABLE"}}
    assert session_stub.added_rows == []
