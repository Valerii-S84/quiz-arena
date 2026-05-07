from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import promo_audit, promo_reads, promo_writes, promo_writes_status
from app.api.routes.admin.promo_models import (
    PromoBulkCreateRequest,
    PromoCreateRequest,
    PromoPatchRequest,
)
from tests.type_helpers import AsyncBeginContext, AsyncSessionStub, build_promo_code

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def _session_local(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)
    return SimpleNamespace(begin=lambda: AsyncBeginContext(remaining.pop(0)))


def _admin(*, role: str = "admin") -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role=role,
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


def _promo(**overrides: object):
    payload = {
        "id": 77,
        "code_prefix": "SPRING",
        "campaign_name": "Spring sale",
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=365),
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(hours=1),
    }
    payload.update(overrides)
    return build_promo_code(**payload)


__all__ = [
    "AsyncBeginContext",
    "AsyncSessionStub",
    "HTTPException",
    "NOW",
    "PromoBulkCreateRequest",
    "PromoCreateRequest",
    "PromoPatchRequest",
    "SimpleNamespace",
    "UTC",
    "_admin",
    "_promo",
    "_session_local",
    "admin_deps",
    "build_promo_code",
    "cast",
    "datetime",
    "promo_audit",
    "promo_reads",
    "promo_writes",
    "promo_writes_status",
    "pytest",
    "timedelta",
    "uuid4",
]
