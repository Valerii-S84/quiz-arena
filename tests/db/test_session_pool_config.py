from __future__ import annotations

from sqlalchemy.pool import NullPool

from app.db import session as db_session


def test_engine_pool_kwargs_use_null_pool_for_test_env() -> None:
    assert db_session._engine_pool_kwargs("test") == {"poolclass": NullPool}


def test_engine_pool_kwargs_raise_load_capacity_without_changing_default_envs() -> None:
    assert db_session._engine_pool_kwargs("load") == {
        "pool_size": 25,
        "max_overflow": 0,
    }
    assert db_session._engine_pool_kwargs("dev") == {}
    assert db_session._engine_pool_kwargs("prod") == {}
