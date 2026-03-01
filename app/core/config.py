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
    quiz_question_pool_cache_ttl_seconds: int = Field(
        default=300,
        alias="QUIZ_QUESTION_POOL_CACHE_TTL_SECONDS",
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(alias="TELEGRAM_WEBHOOK_SECRET")
    welcome_image_file_id: str = Field(default="", alias="WELCOME_IMAGE_FILE_ID")
    telegram_home_header_file_id: str = Field(default="", alias="TELEGRAM_HOME_HEADER_FILE_ID")
    # Telegram channel target for one-time Kanal-Bonus check (supports @username or chat id).
    bonus_channel_id: str = Field(default="", alias="BONUS_CHANNEL_ID")
    # Optional dedicated bot token for get_chat_member subscription checks.
    bonus_check_bot_token: str = Field(default="", alias="BONUS_CHECK_BOT_TOKEN")
    telegram_webhook_enqueue_timeout_ms: int = Field(
        default=250,
        alias="TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS",
    )
    telegram_update_processing_ttl_seconds: int = Field(
        default=300,
        alias="TELEGRAM_UPDATE_PROCESSING_TTL_SECONDS",
    )
    telegram_update_task_max_retries: int = Field(
        default=7,
        alias="TELEGRAM_UPDATE_TASK_MAX_RETRIES",
    )
    telegram_update_task_retry_backoff_max_seconds: int = Field(
        default=300,
        alias="TELEGRAM_UPDATE_TASK_RETRY_BACKOFF_MAX_SECONDS",
    )
    friend_challenge_ttl_seconds: int = Field(
        default=86_400,
        alias="FRIEND_CHALLENGE_TTL_SECONDS",
    )
    friend_challenge_last_chance_seconds: int = Field(
        default=7_200,
        alias="FRIEND_CHALLENGE_LAST_CHANCE_SECONDS",
    )
    friend_challenge_deadline_batch_size: int = Field(
        default=100,
        alias="FRIEND_CHALLENGE_DEADLINE_BATCH_SIZE",
    )
    friend_challenge_deadline_scan_interval_seconds: int = Field(
        default=300,
        alias="FRIEND_CHALLENGE_DEADLINE_SCAN_INTERVAL_SECONDS",
    )
    duel_pending_ttl_hours: int = Field(
        default=6,
        alias="DUEL_PENDING_TTL_HOURS",
    )
    duel_accepted_ttl_hours: int = Field(
        default=48,
        alias="DUEL_ACCEPTED_TTL_HOURS",
    )
    duel_max_active_per_user: int = Field(
        default=10,
        alias="DUEL_MAX_ACTIVE_PER_USER",
    )
    duel_max_new_per_day: int = Field(
        default=20,
        alias="DUEL_MAX_NEW_PER_DAY",
    )
    duel_max_push_per_user: int = Field(
        default=2,
        alias="DUEL_MAX_PUSH_PER_USER",
    )
    tournament_round_ttl_hours: int = Field(default=24, alias="TOURNAMENT_ROUND_TTL_HOURS")
    tournament_max_participants: int = Field(default=8, alias="TOURNAMENT_MAX_PARTICIPANTS")
    tournament_min_participants: int = Field(default=2, alias="TOURNAMENT_MIN_PARTICIPANTS")
    tournament_rounds: int = Field(default=3, alias="TOURNAMENT_ROUNDS")
    daily_cup_registration_open: str = Field(default="12:00", alias="DAILY_CUP_REGISTRATION_OPEN")
    daily_cup_registration_close: str = Field(default="14:00", alias="DAILY_CUP_REGISTRATION_CLOSE")
    daily_cup_round_duration_minutes: int = Field(
        default=120, alias="DAILY_CUP_ROUND_DURATION_MINUTES"
    )
    daily_cup_min_participants: int = Field(default=4, alias="DAILY_CUP_MIN_PARTICIPANTS")
    daily_cup_timezone: str = Field(default="Europe/Berlin", alias="DAILY_CUP_TIMEZONE")
    daily_challenge_precompute_hour_berlin: int = Field(
        default=0,
        alias="DAILY_CHALLENGE_PRECOMPUTE_HOUR_BERLIN",
    )
    daily_challenge_precompute_minute_berlin: int = Field(
        default=0,
        alias="DAILY_CHALLENGE_PRECOMPUTE_MINUTE_BERLIN",
    )
    daily_challenge_push_hour_berlin: int = Field(
        default=8,
        alias="DAILY_CHALLENGE_PUSH_HOUR_BERLIN",
    )
    daily_challenge_push_minute_berlin: int = Field(
        default=0,
        alias="DAILY_CHALLENGE_PUSH_MINUTE_BERLIN",
    )
    daily_challenge_push_batch_size: int = Field(
        default=200,
        alias="DAILY_CHALLENGE_PUSH_BATCH_SIZE",
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
    retention_outbox_events_days: int = Field(
        default=30,
        alias="RETENTION_OUTBOX_EVENTS_DAYS",
    )
    retention_analytics_events_days: int = Field(
        default=90,
        alias="RETENTION_ANALYTICS_EVENTS_DAYS",
    )
    retention_cleanup_batch_size: int = Field(
        default=5000,
        alias="RETENTION_CLEANUP_BATCH_SIZE",
    )
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
    ops_alert_pagerduty_routing_key: str = Field(
        default="", alias="OPS_ALERT_PAGERDUTY_ROUTING_KEY"
    )
    ops_alert_escalation_policy_json: str = Field(
        default="", alias="OPS_ALERT_ESCALATION_POLICY_JSON"
    )
    offers_alert_window_hours: int = Field(default=24, alias="OFFERS_ALERT_WINDOW_HOURS")
    offers_alert_min_impressions: int = Field(default=50, alias="OFFERS_ALERT_MIN_IMPRESSIONS")
    offers_alert_min_conversion_rate: float = Field(
        default=0.03, alias="OFFERS_ALERT_MIN_CONVERSION_RATE"
    )
    offers_alert_max_dismiss_rate: float = Field(
        default=0.60, alias="OFFERS_ALERT_MAX_DISMISS_RATE"
    )
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
    promo_secret_pepper: str = Field(
        default="dev_promo_pepper_change_me", alias="PROMO_SECRET_PEPPER"
    )

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")

    celery_broker_url: str = Field(alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(alias="CELERY_RESULT_BACKEND")

    @property
    def resolved_welcome_image_file_id(self) -> str:
        return self.welcome_image_file_id.strip() or self.telegram_home_header_file_id.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
