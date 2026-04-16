from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from typing import Any

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config_admin import AdminSettingsMixin
from app.core.config_messaging import MessagingSettingsMixin
from app.core.config_runtime import RuntimeSettingsMixin


class Settings(
    MessagingSettingsMixin,
    AdminSettingsMixin,
    RuntimeSettingsMixin,
    BaseSettings,
):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @staticmethod
    def _normalize_required_secret(value: Any, *, env_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{env_name} must be configured")
        return normalized

    @field_validator(
        "admin_jwt_secret",
        "admin_refresh_secret",
        "internal_api_token",
        "promo_secret_pepper",
        mode="before",
    )
    @classmethod
    def _validate_required_secrets(cls, value: Any, info: ValidationInfo) -> str:
        field_name = info.field_name
        if field_name is None:
            raise ValueError("Required secret validator must be bound to a field")
        env_name = field_name.upper()
        return cls._normalize_required_secret(value, env_name=env_name)

    @field_validator("promo_encryption_key", mode="before")
    @classmethod
    def _validate_promo_encryption_key(cls, value: Any) -> str:
        normalized = cls._normalize_required_secret(value, env_name="PROMO_ENCRYPTION_KEY")
        padding = "=" * (-len(normalized) % 4)
        try:
            decoded = base64.urlsafe_b64decode(f"{normalized}{padding}".encode("ascii"))
        except (ValueError, binascii.Error) as exc:
            raise ValueError(
                "PROMO_ENCRYPTION_KEY must be a urlsafe base64-encoded 32-byte key"
            ) from exc
        if len(decoded) != 32:
            raise ValueError("PROMO_ENCRYPTION_KEY must be a urlsafe base64-encoded 32-byte key")
        return normalized

    @field_validator("admin_password_hash", "admin_password_plain", mode="before")
    @classmethod
    def _normalize_optional_admin_password(cls, value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_admin_password_source(self) -> Settings:
        if self.admin_password_hash or self.admin_password_plain:
            return self
        raise ValueError("Either ADMIN_PASSWORD_HASH or ADMIN_PASSWORD_PLAIN must be configured")

    @property
    def resolved_welcome_image_file_id(self) -> str:
        return self.welcome_image_file_id.strip() or self.telegram_home_header_file_id.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
