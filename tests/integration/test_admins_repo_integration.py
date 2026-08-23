from __future__ import annotations

import pytest

from app.db.repo.admins_repo import AdminsRepo
from app.db.session import SessionLocal


@pytest.mark.asyncio
async def test_admins_repo_get_by_email_returns_none_for_missing_admin() -> None:
    async with SessionLocal.begin() as session:
        admin = await AdminsRepo.get_by_email(session, email="missing@example.com")

    assert admin is None


@pytest.mark.asyncio
async def test_admins_repo_get_or_create_never_updates_existing_authority() -> None:
    email = "admin@example.com"

    async with SessionLocal.begin() as session:
        created = await AdminsRepo.get_or_create(
            session,
            email=email,
            role="admin",
        )

    assert created.email == email
    assert created.role == "admin"
    assert created.enabled is False
    assert created.created_at == created.updated_at

    async with SessionLocal.begin() as session:
        updated = await AdminsRepo.get_or_create(
            session,
            email=email,
            role="super_admin",
            enabled=True,
        )

    assert updated.id == created.id
    assert updated.email == email
    assert updated.role == "admin"
    assert updated.enabled is False
    assert updated.updated_at == created.updated_at

    async with SessionLocal.begin() as session:
        loaded = await AdminsRepo.get_by_email(session, email=email)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.role == "admin"
    assert loaded.enabled is False
