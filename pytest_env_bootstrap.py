from __future__ import annotations

import importlib
import sys

from app.core.test_env import apply_test_env_defaults

_BOOTSTRAPPED = False


def bootstrap_pytest_env() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    apply_test_env_defaults(force_database_url_to_test=True)

    if "app.core.config" in sys.modules:
        config_module = sys.modules["app.core.config"]
        get_settings = getattr(config_module, "get_settings", None)
        if callable(get_settings):
            get_settings.cache_clear()
            setattr(config_module, "settings", get_settings())

    if "app.db.session" in sys.modules:
        importlib.reload(sys.modules["app.db.session"])

    _BOOTSTRAPPED = True
