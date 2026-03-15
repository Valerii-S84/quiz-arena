from __future__ import annotations

from app.core.config import get_settings

from .constants import (
    OPS_UI_FORM_CONTENT_TYPE,
    OPS_UI_LOGIN_FAILED_WINDOW_SECONDS,
    OPS_UI_LOGIN_FAILURE_DELAY_SECONDS,
    OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS,
    OPS_UI_LOGIN_PAGE,
    OPS_UI_PAGES,
    OPS_UI_ROOT,
    OPS_UI_SESSION_MAX_AGE_SECONDS,
    OPS_UI_STATIC_DIR,
)
from .routes import (
    get_ops_login_page,
    get_ops_notifications_page,
    get_ops_promo_page,
    get_ops_referrals_page,
    get_ops_root,
    login_ops_ui,
    logout_ops_ui,
    router,
)
from .state import _LOGIN_FAILED_ATTEMPTS, _LOGIN_THROTTLE_LOCK

__all__ = [
    "OPS_UI_FORM_CONTENT_TYPE",
    "OPS_UI_LOGIN_FAILED_WINDOW_SECONDS",
    "OPS_UI_LOGIN_FAILURE_DELAY_SECONDS",
    "OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS",
    "OPS_UI_LOGIN_PAGE",
    "OPS_UI_PAGES",
    "OPS_UI_ROOT",
    "OPS_UI_SESSION_MAX_AGE_SECONDS",
    "OPS_UI_STATIC_DIR",
    "_LOGIN_FAILED_ATTEMPTS",
    "_LOGIN_THROTTLE_LOCK",
    "get_ops_login_page",
    "get_ops_notifications_page",
    "get_ops_promo_page",
    "get_ops_referrals_page",
    "get_ops_root",
    "get_settings",
    "login_ops_ui",
    "logout_ops_ui",
    "router",
]
