from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes import public_contact as public_contact_routes
from app.api.routes import public_site as public_site_routes
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc


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


def test_stats_alias_maps_public_metrics(monkeypatch) -> None:
    monkeypatch.setattr(public_site_routes, "_collect_public_metrics", _metrics_stub)

    client = TestClient(app)
    response = client.get("/stats")

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


def test_contact_alias_student_request_is_accepted(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(public_contact_routes, "SessionLocal", session_stub)
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


@pytest.mark.asyncio
async def test_collect_public_metrics_counts_only_completed_quizzes() -> None:
    started_at = datetime(2026, 4, 6, 12, 0, tzinfo=UTC)
    before_metrics = await public_site_routes._collect_public_metrics()

    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=stable_telegram_user_id(
                prefix=81_000_000_000, seed="public-site-stats"
            ),
            referral_code="PUBSTATS01",
            username="public-site-stats",
            first_name="Public",
            referred_by_user_id=None,
        )
        session.add_all(
            [
                QuizSession(
                    id=uuid4(),
                    user_id=int(user.id),
                    mode_code="QUICK_MIX_A1A2",
                    source="MENU",
                    status="COMPLETED",
                    energy_cost_total=1,
                    question_id="q-public-1",
                    friend_challenge_id=None,
                    friend_challenge_round=None,
                    started_at=started_at,
                    completed_at=started_at + timedelta(minutes=1),
                    local_date_berlin=date(2026, 4, 6),
                    idempotency_key="public-site-stats:completed",
                ),
                QuizSession(
                    id=uuid4(),
                    user_id=int(user.id),
                    mode_code="QUICK_MIX_A1A2",
                    source="MENU",
                    status="STARTED",
                    energy_cost_total=1,
                    question_id="q-public-2",
                    friend_challenge_id=None,
                    friend_challenge_round=None,
                    started_at=started_at + timedelta(minutes=2),
                    completed_at=None,
                    local_date_berlin=date(2026, 4, 6),
                    idempotency_key="public-site-stats:started",
                ),
            ]
        )

    metrics = await public_site_routes._collect_public_metrics()

    assert metrics["quizzes_total"] == before_metrics["quizzes_total"] + 1
