from functools import lru_cache

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

    @property
    def resolved_welcome_image_file_id(self) -> str:
        return self.welcome_image_file_id.strip() or self.telegram_home_header_file_id.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
