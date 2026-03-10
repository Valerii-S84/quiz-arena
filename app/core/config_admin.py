from __future__ import annotations

from pydantic import Field


class AdminSettingsMixin:
    admin_frontend_origin: str = Field(
        default="http://localhost:3000",
        alias="ADMIN_FRONTEND_ORIGIN",
    )
    admin_email: str = Field(default="admin@example.com", alias="ADMIN_EMAIL")
    admin_password_hash: str = Field(default="", alias="ADMIN_PASSWORD_HASH")
    admin_password_plain: str = Field(default="admin12345", alias="ADMIN_PASSWORD_PLAIN")
    admin_jwt_secret: str = Field(
        default="dev_admin_jwt_secret_change_me",
        alias="ADMIN_JWT_SECRET",
    )
    admin_refresh_secret: str = Field(
        default="dev_admin_refresh_secret_change_me",
        alias="ADMIN_REFRESH_SECRET",
    )
    admin_2fa_required: bool = Field(default=True, alias="ADMIN_2FA_REQUIRED")
    admin_totp_secret: str = Field(default="", alias="ADMIN_TOTP_SECRET")
    admin_totp_issuer: str = Field(default="Quiz Arena Admin", alias="ADMIN_TOTP_ISSUER")
    admin_access_token_ttl_minutes: int = Field(
        default=15,
        alias="ADMIN_ACCESS_TOKEN_TTL_MINUTES",
    )
    admin_refresh_token_ttl_days: int = Field(default=7, alias="ADMIN_REFRESH_TOKEN_TTL_DAYS")
    admin_role: str = Field(default="admin", alias="ADMIN_ROLE")
    admin_login_rate_limit_attempts: int = Field(
        default=5,
        alias="ADMIN_LOGIN_RATE_LIMIT_ATTEMPTS",
    )
    admin_login_rate_limit_window_minutes: int = Field(
        default=15,
        alias="ADMIN_LOGIN_RATE_LIMIT_WINDOW_MINUTES",
    )
    ops_alert_webhook_url: str = Field(default="", alias="OPS_ALERT_WEBHOOK_URL")
    ops_alert_slack_webhook_url: str = Field(default="", alias="OPS_ALERT_SLACK_WEBHOOK_URL")
    ops_alert_pagerduty_events_url: str = Field(default="", alias="OPS_ALERT_PAGERDUTY_EVENTS_URL")
    ops_alert_pagerduty_routing_key: str = Field(
        default="",
        alias="OPS_ALERT_PAGERDUTY_ROUTING_KEY",
    )
    ops_alert_escalation_policy_json: str = Field(
        default="",
        alias="OPS_ALERT_ESCALATION_POLICY_JSON",
    )
    offers_alert_window_hours: int = Field(default=24, alias="OFFERS_ALERT_WINDOW_HOURS")
    offers_alert_min_impressions: int = Field(default=50, alias="OFFERS_ALERT_MIN_IMPRESSIONS")
    offers_alert_min_conversion_rate: float = Field(
        default=0.03,
        alias="OFFERS_ALERT_MIN_CONVERSION_RATE",
    )
    offers_alert_max_dismiss_rate: float = Field(
        default=0.60,
        alias="OFFERS_ALERT_MAX_DISMISS_RATE",
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
