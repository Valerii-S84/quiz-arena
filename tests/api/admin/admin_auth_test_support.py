from __future__ import annotations

from typing import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.main import app
from tests.type_helpers import build_settings


def settings_stub(*, two_fa_required: bool = True):
    return build_settings(
        app_env="dev",
        admin_role="admin",
        admin_2fa_required=two_fa_required,
        admin_login_rate_limit_window_minutes=5,
        admin_login_rate_limit_attempts=3,
        admin_access_token_ttl_minutes=15,
        redis_url="redis://localhost:6379/15",
        internal_api_trusted_proxies="127.0.0.1/32",
    )


def principal_stub(*, two_factor_verified: bool = False) -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=two_factor_verified,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


__all__ = ["client", "principal_stub", "settings_stub"]
