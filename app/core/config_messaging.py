from __future__ import annotations

from pydantic import Field


class MessagingSettingsMixin:
    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(alias="TELEGRAM_WEBHOOK_SECRET")
    telegram_public_bot_username: str = Field(
        default="Deine_Deutsch_Quiz_bot",
        alias="TELEGRAM_PUBLIC_BOT_USERNAME",
    )
    welcome_image_file_id: str = Field(default="", alias="WELCOME_IMAGE_FILE_ID")
    telegram_home_header_file_id: str = Field(default="", alias="TELEGRAM_HOME_HEADER_FILE_ID")
    bonus_channel_id: str = Field(default="", alias="BONUS_CHANNEL_ID")
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
    friend_challenge_ttl_seconds: int = Field(default=86_400, alias="FRIEND_CHALLENGE_TTL_SECONDS")
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
    duel_pending_ttl_hours: int = Field(default=6, alias="DUEL_PENDING_TTL_HOURS")
    duel_accepted_ttl_hours: int = Field(default=48, alias="DUEL_ACCEPTED_TTL_HOURS")
    duel_max_active_per_user: int = Field(default=10, alias="DUEL_MAX_ACTIVE_PER_USER")
    duel_max_new_per_day: int = Field(default=20, alias="DUEL_MAX_NEW_PER_DAY")
    duel_max_push_per_user: int = Field(default=2, alias="DUEL_MAX_PUSH_PER_USER")
    tournament_friends_enabled: bool = Field(default=False, alias="TOURNAMENT_FRIENDS_ENABLED")
    tournament_round_ttl_hours: int = Field(default=24, alias="TOURNAMENT_ROUND_TTL_HOURS")
    tournament_max_participants: int = Field(default=8, alias="TOURNAMENT_MAX_PARTICIPANTS")
    tournament_min_participants: int = Field(default=2, alias="TOURNAMENT_MIN_PARTICIPANTS")
    tournament_rounds: int = Field(default=3, alias="TOURNAMENT_ROUNDS")
    daily_cup_registration_open: str = Field(default="16:00", alias="DAILY_CUP_REGISTRATION_OPEN")
    daily_cup_registration_close: str = Field(default="18:00", alias="DAILY_CUP_REGISTRATION_CLOSE")
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
