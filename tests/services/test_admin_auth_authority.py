from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError

from app.db.models.admins import Admin
from app.services.admin import auth_authority
from app.services.admin.auth_common import AdminAuthStateError


class _ReadContext:
    def __init__(self, session: object) -> None:
        self._session = session
        self.exited = False

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self.exited = True
        return False


class _SessionLocal:
    def __init__(self, context: _ReadContext) -> None:
        self._context = context

    def begin(self) -> _ReadContext:
        return self._context


def _admin(
    *,
    email: str = "admin@example.com",
    role: str = "admin",
    enabled: bool = True,
) -> Admin:
    return Admin(
        id=uuid4(),
        email=email,
        role=role,
        enabled=enabled,
    )


def _stub_authority_read(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: Admin | None = None,
    error: Exception | None = None,
) -> _ReadContext:
    context = _ReadContext(object())

    async def _get_by_email(session: object, *, email: str) -> Admin | None:
        del session, email
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(auth_authority, "SessionLocal", _SessionLocal(context))
    monkeypatch.setattr(auth_authority.AdminsRepo, "get_by_email", _get_by_email)
    return context


async def test_resolver_returns_enabled_database_authority_after_read_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _admin(email=" Admin@Example.com ", role="super-admin")
    context = _stub_authority_read(monkeypatch, result=admin)

    authority = await auth_authority.resolve_current_admin_authority(
        email="admin@example.com",
        expected_role="super_admin",
    )

    assert authority == auth_authority.CurrentAdminAuthority(
        id=admin.id,
        email="admin@example.com",
        role="super_admin",
        enabled=True,
    )
    assert context.exited is True


async def test_resolver_uses_database_role_when_login_has_no_expected_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _admin(role="super_admin")
    _stub_authority_read(monkeypatch, result=admin)

    authority = await auth_authority.resolve_current_admin_authority(email=admin.email)

    assert authority is not None
    assert authority.role == "super_admin"


@pytest.mark.parametrize(
    "admin",
    [
        None,
        _admin(enabled=False),
        _admin(email="other@example.com"),
        _admin(role="owner"),
    ],
    ids=["missing", "disabled", "email-mismatch", "invalid-db-role"],
)
async def test_resolver_denies_non_authoritative_identity(
    monkeypatch: pytest.MonkeyPatch,
    admin: Admin | None,
) -> None:
    _stub_authority_read(monkeypatch, result=admin)

    authority = await auth_authority.resolve_current_admin_authority(
        email="admin@example.com",
        expected_role="admin",
    )

    assert authority is None


async def test_resolver_denies_stale_role_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_authority_read(monkeypatch, result=_admin(role="super_admin"))

    authority = await auth_authority.resolve_current_admin_authority(
        email="admin@example.com",
        expected_role="admin",
    )

    assert authority is None


async def test_resolver_denies_normalized_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_authority_read(monkeypatch, error=MultipleResultsFound())

    authority = await auth_authority.resolve_current_admin_authority(
        email="admin@example.com",
        expected_role="admin",
    )

    assert authority is None


async def test_resolver_maps_database_outage_to_auth_state_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _stub_authority_read(monkeypatch, error=SQLAlchemyError("down"))

    with pytest.raises(AdminAuthStateError):
        await auth_authority.resolve_current_admin_authority(
            email="admin@example.com",
            expected_role="admin",
        )

    assert context.exited is True
