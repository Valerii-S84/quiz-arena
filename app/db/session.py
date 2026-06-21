from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

_LOAD_DB_POOL_SIZE = 25
_LOAD_DB_MAX_OVERFLOW = 0


def _engine_pool_kwargs(app_env: str) -> dict[str, object]:
    if app_env == "test":
        return {"poolclass": NullPool}
    if app_env == "load":
        return {
            "pool_size": _LOAD_DB_POOL_SIZE,
            "max_overflow": _LOAD_DB_MAX_OVERFLOW,
        }
    return {}


engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "dev",
    pool_pre_ping=True,
    **_engine_pool_kwargs(settings.app_env),
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()
