from __future__ import annotations

import importlib
import os
import sys
import tempfile

TEST_DATABASE_URL = "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
TEST_REDIS_URL = "redis://localhost:6379/15"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("TMPDIR", tempfile.gettempdir())
os.environ.setdefault("REDIS_URL", TEST_REDIS_URL)
os.environ.setdefault("CELERY_BROKER_URL", TEST_REDIS_URL)
os.environ.setdefault("CELERY_RESULT_BACKEND", TEST_REDIS_URL)
os.environ.setdefault("APP_ENV", "test")

if "app.core.config" in sys.modules:
    config_module = sys.modules["app.core.config"]
    get_settings = getattr(config_module, "get_settings", None)
    if callable(get_settings):
        get_settings.cache_clear()
        config_module.settings = get_settings()

if "app.db.session" in sys.modules:
    importlib.reload(sys.modules["app.db.session"])
