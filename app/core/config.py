from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="dev", alias="APP_ENV")
    enable_openapi_docs: bool = Field(default=True, alias="ENABLE_OPENAPI_DOCS")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(alias="TELEGRAM_WEBHOOK_SECRET")
    internal_api_token: str = Field(
        default="dev_internal_token_change_me",
        alias="INTERNAL_API_TOKEN",
    )
    internal_api_allowlist: str = Field(
        default="127.0.0.1/32,::1/128",
        alias="INTERNAL_API_ALLOWLIST",
    )
    internal_api_trusted_proxies: str = Field(
        default="127.0.0.1/32,::1/128",
        alias="INTERNAL_API_TRUSTED_PROXIES",
    )
    ops_alert_webhook_url: str = Field(default="", alias="OPS_ALERT_WEBHOOK_URL")
    ops_alert_slack_webhook_url: str = Field(default="", alias="OPS_ALERT_SLACK_WEBHOOK_URL")
    ops_alert_pagerduty_events_url: str = Field(default="", alias="OPS_ALERT_PAGERDUTY_EVENTS_URL")
    ops_alert_pagerduty_routing_key: str = Field(default="", alias="OPS_ALERT_PAGERDUTY_ROUTING_KEY")
    ops_alert_escalation_policy_json: str = Field(default="", alias="OPS_ALERT_ESCALATION_POLICY_JSON")
    offers_alert_window_hours: int = Field(default=24, alias="OFFERS_ALERT_WINDOW_HOURS")
    offers_alert_min_impressions: int = Field(default=50, alias="OFFERS_ALERT_MIN_IMPRESSIONS")
    offers_alert_min_conversion_rate: float = Field(default=0.03, alias="OFFERS_ALERT_MIN_CONVERSION_RATE")
    offers_alert_max_dismiss_rate: float = Field(default=0.60, alias="OFFERS_ALERT_MAX_DISMISS_RATE")
    offers_alert_max_impressions_per_user: float = Field(
        default=4.0,
        alias="OFFERS_ALERT_MAX_IMPRESSIONS_PER_USER",
    )
    referrals_alert_window_hours: int = Field(default=24, alias="REFERRALS_ALERT_WINDOW_HOURS")
    referrals_alert_min_started: int = Field(default=20, alias="REFERRALS_ALERT_MIN_STARTED")
    referrals_alert_max_fraud_rejected_rate: float = Field(
        default=0.25,
        alias="REFERRALS_ALERT_MAX_FRAUD_REJECTED_RATE",
    )
    referrals_alert_max_rejected_fraud_total: int = Field(
        default=10,
        alias="REFERRALS_ALERT_MAX_REJECTED_FRAUD_TOTAL",
    )
    referrals_alert_max_referrer_rejected_fraud: int = Field(
        default=3,
        alias="REFERRALS_ALERT_MAX_REFERRER_REJECTED_FRAUD",
    )
    promo_secret_pepper: str = Field(default="dev_promo_pepper_change_me", alias="PROMO_SECRET_PEPPER")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")

    celery_broker_url: str = Field(alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(alias="CELERY_RESULT_BACKEND")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
