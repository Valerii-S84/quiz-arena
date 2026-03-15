from __future__ import annotations

from pathlib import Path

OPS_UI_ROOT = Path(__file__).resolve().parents[3] / "ops_ui" / "site"
OPS_UI_STATIC_DIR = OPS_UI_ROOT / "static"
OPS_UI_LOGIN_PAGE = OPS_UI_ROOT / "login.html"
OPS_UI_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
OPS_UI_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
OPS_UI_LOGIN_FAILED_WINDOW_SECONDS = 5 * 60
OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS = 8
OPS_UI_LOGIN_FAILURE_DELAY_SECONDS = 0.4
OPS_UI_PAGES = {
    "promo": OPS_UI_ROOT / "promo.html",
    "referrals": OPS_UI_ROOT / "referrals.html",
    "notifications": OPS_UI_ROOT / "notifications.html",
}
