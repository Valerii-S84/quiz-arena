from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_attempts import PromoAttempt
from app.db.repo.promo_repo import PromoRepo
from app.db.session import SessionLocal


async def record_attempt(
    session: AsyncSession,
    *,
    user_id: int,
    normalized_code_hash: str,
    result: str,
    now_utc: datetime,
    metadata: dict[str, object] | None = None,
) -> None:
    await PromoRepo.create_attempt(
        session,
        attempt=PromoAttempt(
            user_id=user_id,
            normalized_code_hash=normalized_code_hash,
            result=result,
            source="API",
            attempted_at=now_utc,
            metadata_=metadata or {},
        ),
    )


async def record_failed_attempt(
    *,
    user_id: int,
    normalized_code_hash: str,
    result: str,
    now_utc: datetime,
    metadata: dict[str, object] | None = None,
) -> None:
    async with SessionLocal.begin() as attempt_session:
        await record_attempt(
            attempt_session,
            user_id=user_id,
            normalized_code_hash=normalized_code_hash,
            result=result,
            now_utc=now_utc,
            metadata=metadata,
        )
