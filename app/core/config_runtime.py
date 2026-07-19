from __future__ import annotations

from pydantic import Field


class RuntimeSettingsMixin:
    app_env: str = Field(default="dev", alias="APP_ENV")
    enable_openapi_docs: bool = Field(default=True, alias="ENABLE_OPENAPI_DOCS")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    quiz_question_pool_cache_ttl_seconds: int = Field(
        default=300,
        alias="QUIZ_QUESTION_POOL_CACHE_TTL_SECONDS",
    )
    global_best_streak_cache_ttl_seconds: int = Field(
        default=300,
        alias="GLOBAL_BEST_STREAK_CACHE_TTL_SECONDS",
    )
    telegram_updates_alert_window_minutes: int = Field(
        default=15,
        alias="TELEGRAM_UPDATES_ALERT_WINDOW_MINUTES",
    )
    telegram_updates_stuck_alert_min_minutes: int = Field(
        default=10,
        alias="TELEGRAM_UPDATES_STUCK_ALERT_MIN_MINUTES",
    )
    telegram_updates_retry_spike_threshold: int = Field(
        default=25,
        alias="TELEGRAM_UPDATES_RETRY_SPIKE_THRESHOLD",
    )
    telegram_updates_failed_final_spike_threshold: int = Field(
        default=3,
        alias="TELEGRAM_UPDATES_FAILED_FINAL_SPIKE_THRESHOLD",
    )
    telegram_updates_observability_top_stuck_limit: int = Field(
        default=10,
        alias="TELEGRAM_UPDATES_OBSERVABILITY_TOP_STUCK_LIMIT",
    )
    retention_processed_updates_days: int = Field(
        default=14,
        alias="RETENTION_PROCESSED_UPDATES_DAYS",
    )
    retention_outbox_events_days: int = Field(default=30, alias="RETENTION_OUTBOX_EVENTS_DAYS")
    retention_analytics_events_days: int = Field(
        default=90, alias="RETENTION_ANALYTICS_EVENTS_DAYS"
    )
    retention_cleanup_batch_size: int = Field(default=5000, alias="RETENTION_CLEANUP_BATCH_SIZE")
    retention_cleanup_max_batches_per_table: int = Field(
        default=20,
        alias="RETENTION_CLEANUP_MAX_BATCHES_PER_TABLE",
    )
    retention_cleanup_max_runtime_seconds: int = Field(
        default=45,
        alias="RETENTION_CLEANUP_MAX_RUNTIME_SECONDS",
    )
    retention_cleanup_batch_sleep_min_ms: int = Field(
        default=0,
        alias="RETENTION_CLEANUP_BATCH_SLEEP_MIN_MS",
    )
    retention_cleanup_batch_sleep_max_ms: int = Field(
        default=0,
        alias="RETENTION_CLEANUP_BATCH_SLEEP_MAX_MS",
    )
    retention_cleanup_schedule_seconds: int = Field(
        default=3600,
        alias="RETENTION_CLEANUP_SCHEDULE_SECONDS",
    )
    retention_cleanup_schedule_hour_berlin: int = Field(
        default=3,
        alias="RETENTION_CLEANUP_SCHEDULE_HOUR_BERLIN",
    )
    retention_cleanup_schedule_minute_berlin: int = Field(
        default=15,
        alias="RETENTION_CLEANUP_SCHEDULE_MINUTE_BERLIN",
    )
    website_analytics_visitor_salt: str = Field(
        default="",
        alias="WEBSITE_ANALYTICS_VISITOR_SALT",
    )
    website_analytics_rate_limit_per_minute: int = Field(
        default=180,
        alias="WEBSITE_ANALYTICS_RATE_LIMIT_PER_MINUTE",
    )
    internal_api_token: str = Field(alias="INTERNAL_API_TOKEN")
    internal_api_allowlist: str = Field(
        default="127.0.0.1/32,::1/128",
        alias="INTERNAL_API_ALLOWLIST",
    )
    internal_api_trusted_proxies: str = Field(
        default="127.0.0.1/32,::1/128",
        alias="INTERNAL_API_TRUSTED_PROXIES",
    )
    promo_secret_pepper: str = Field(alias="PROMO_SECRET_PEPPER")
    promo_encryption_key: str = Field(alias="PROMO_ENCRYPTION_KEY")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    celery_broker_url: str = Field(alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(alias="CELERY_RESULT_BACKEND")
