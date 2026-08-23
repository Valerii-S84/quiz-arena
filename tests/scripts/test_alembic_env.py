from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


class _FakeTransaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_alembic_env_bootstraps_database_url_from_test_database_url(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test",
    )

    configured: dict[str, object] = {}

    fake_context = SimpleNamespace(
        config=SimpleNamespace(
            attributes={},
            config_file_name=None,
            config_ini_section="alembic",
            set_main_option=lambda key, value: configured.setdefault(key, value),
            get_section=lambda section, default: {},
        ),
        configure=lambda **kwargs: configured.setdefault("configure", kwargs),
        begin_transaction=lambda: _FakeTransaction(),
        run_migrations=lambda: configured.setdefault("ran_migrations", True),
        is_offline_mode=lambda: True,
    )

    alembic_module = ModuleType("alembic")
    setattr(alembic_module, "context", fake_context)

    app_module = ModuleType("app")
    core_module = ModuleType("app.core")
    db_module = ModuleType("app.db")
    db_models_module = ModuleType("app.db.models")
    db_models_base_module = ModuleType("app.db.models.base")
    config_module = ModuleType("app.core.config")
    metadata = object()

    setattr(db_module, "models", db_models_module)
    setattr(db_models_base_module, "Base", SimpleNamespace(metadata=metadata))

    def fake_get_settings() -> SimpleNamespace:
        return SimpleNamespace(
            admin_email="admin@example.com",
            database_url=os.environ["DATABASE_URL"],
        )

    setattr(config_module, "get_settings", fake_get_settings)

    original_modules = {
        name: sys.modules.get(name)
        for name in (
            "alembic",
            "app",
            "app.core",
            "app.core.config",
            "app.db",
            "app.db.models",
            "app.db.models.base",
        )
    }

    sys.modules["alembic"] = alembic_module
    sys.modules["app"] = app_module
    sys.modules["app.core"] = core_module
    sys.modules["app.core.config"] = config_module
    sys.modules["app.db"] = db_module
    sys.modules["app.db.models"] = db_models_module
    sys.modules["app.db.models.base"] = db_models_base_module

    try:
        env_path = Path(__file__).resolve().parents[2] / "alembic" / "env.py"
        spec = importlib.util.spec_from_file_location("test_alembic_env_module", env_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, original_module in original_modules.items():
            if original_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original_module

    assert (
        configured["sqlalchemy.url"]
        == "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
    )
    assert configured["configure"] == {
        "url": "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test",
        "target_metadata": metadata,
        "literal_binds": True,
        "compare_type": True,
    }
    assert fake_context.config.attributes == {"admin_bootstrap_email": "admin@example.com"}
