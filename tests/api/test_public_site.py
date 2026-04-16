from fastapi.testclient import TestClient

from app.api.routes import public_contact as public_contact_routes
from app.api.routes import public_site as public_site_routes
from app.main import app
from app.services.contact_rate_limit import ContactRateLimitStateError


async def _metrics_stub() -> dict[str, object]:
    return {
        "users_total": 1234,
        "quizzes_total": 5678,
        "purchases_total": 0,
        "revenue_stars_total": 0,
        "revenue_eur_total": 0.0,
    }


async def _allow_contact_submission_slot(**kwargs) -> bool:
    del kwargs
    return False


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
    monkeypatch.setattr(
        public_contact_routes,
        "consume_contact_submission_slot",
        _allow_contact_submission_slot,
    )
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
    monkeypatch.setattr(
        public_contact_routes,
        "consume_contact_submission_slot",
        _allow_contact_submission_slot,
    )
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
    monkeypatch.setattr(
        public_contact_routes,
        "consume_contact_submission_slot",
        _allow_contact_submission_slot,
    )
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
    monkeypatch.setattr(
        public_contact_routes,
        "consume_contact_submission_slot",
        _allow_contact_submission_slot,
    )
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
    monkeypatch.setattr(
        public_contact_routes,
        "consume_contact_submission_slot",
        _allow_contact_submission_slot,
    )
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


def test_contact_honeypot_payload_is_silently_ignored(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    monkeypatch.setattr(
        public_contact_routes,
        "consume_contact_submission_slot",
        _allow_contact_submission_slot,
    )
    client = TestClient(app)

    response = client.post(
        "/api/contact",
        json={
            "type": "student",
            "name": "Bot",
            "contact": "@bot",
            "ageGroup": "16-25",
            "level": "A2",
            "goals": ["Alltagssprache"],
            "format": "Individuell mit Lehrkraft",
            "timeSlots": ["Abend"],
            "frequency": "2x pro Woche",
            "company": "Spam Corp",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert not session_stub.added_rows


def test_contact_rate_limit_triggers_after_threshold_and_stops_db_writes(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    call_count = {"count": 0}

    async def _consume_contact_submission_slot(**kwargs) -> bool:
        del kwargs
        call_count["count"] += 1
        return call_count["count"] > 2

    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    monkeypatch.setattr(
        public_contact_routes,
        "consume_contact_submission_slot",
        _consume_contact_submission_slot,
    )
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

    first = client.post("/api/contact", json=payload)
    second = client.post("/api/contact", json=payload)
    third = client.post("/api/contact", json=payload)
    fourth = client.post("/api/contact", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert third.status_code == 429
    assert fourth.status_code == 429
    assert len(session_stub.added_rows) == 2


def test_contact_returns_503_when_rate_limit_state_is_unavailable(monkeypatch) -> None:
    session_stub = _SessionLocalStub()

    async def _unavailable(**kwargs) -> bool:
        del kwargs
        raise ContactRateLimitStateError("down")

    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
    monkeypatch.setattr(public_contact_routes, "consume_contact_submission_slot", _unavailable)
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
    assert response.json() == {"detail": {"code": "E_RATE_LIMIT_UNAVAILABLE"}}
    assert not session_stub.added_rows
