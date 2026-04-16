from __future__ import annotations

from app.services.admin import auth as admin_auth
from app.services.admin import auth_state as admin_auth_state
from app.services.admin import auth_totp as admin_auth_totp
from tests.type_helpers import build_settings


class CookieResponse:
    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []

    def set_cookie(self, **kwargs: object) -> None:
        self.set_calls.append(kwargs)

    def delete_cookie(self, **kwargs: object) -> None:
        self.delete_calls.append(kwargs)


class RedisClient:
    def __init__(
        self,
        *,
        get_value: object = None,
        values: dict[str, object] | None = None,
        get_error: Exception | None = None,
        set_error: Exception | None = None,
        ping_error: Exception | None = None,
    ) -> None:
        self.get_value = get_value
        self.values = values or {}
        self.get_error = get_error
        self.set_error = set_error
        self.ping_error = ping_error
        self.set_calls: list[dict[str, object]] = []

    async def ping(self) -> None:
        if self.ping_error is not None:
            raise self.ping_error

    async def get(self, key: str) -> object:
        if self.get_error is not None:
            raise self.get_error
        if key in self.values:
            return self.values[key]
        if key == "qa_admin:totp_secret":
            return self.get_value
        return None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if self.set_error is not None:
            raise self.set_error
        self.values[key] = value
        self.set_calls.append({"key": key, "value": value, "ex": ex})

    async def aclose(self) -> None:
        return None


def settings_stub(**overrides: object):
    return build_settings(**overrides)


def reset_admin_auth_redis_client() -> None:
    admin_auth_state._redis_client = None
    admin_auth_state._redis_client_loop_id = None


__all__ = [
    "CookieResponse",
    "RedisClient",
    "admin_auth",
    "admin_auth_state",
    "admin_auth_totp",
    "reset_admin_auth_redis_client",
    "settings_stub",
]
