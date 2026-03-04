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


def test_api_stats_maps_public_metrics(monkeypatch) -> None:
    monkeypatch.setattr(public_site_routes, "_collect_public_metrics", _metrics_stub)

    client = TestClient(app)
    response = client.get("/api/stats")

    assert response.status_code == 200
    assert response.json() == {"users": 1234, "quizzes": 5678}


def test_contact_student_request_is_accepted(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
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


def test_contact_student_requires_goals(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
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
