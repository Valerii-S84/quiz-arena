from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.offers_repo import OffersRepo
from app.economy.offers.errors import OfferLoggingError
from app.economy.offers.selection import selection_from_impression, selection_from_template
from app.economy.offers.template_selection import select_template_with_caps
from app.economy.offers.time_utils import berlin_now
from app.economy.offers.triggers import build_trigger_codes
from app.economy.offers.types import OfferSelection


async def evaluate_and_log_offer(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
    trigger_event: str | None = None,
) -> OfferSelection | None:
    existing = await OffersRepo.get_by_idempotency_key(
        session,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return selection_from_impression(existing, idempotent_replay=True)

    trigger_codes = await build_trigger_codes(
        session,
        user_id=user_id,
        now_utc=now_utc,
        trigger_event=trigger_event,
    )
    if not trigger_codes:
        return None

    selected_template = await select_template_with_caps(
        session,
        user_id=user_id,
        trigger_codes=trigger_codes,
        now_utc=now_utc,
    )
    if selected_template is None:
        return None

    impression_id = await OffersRepo.insert_impression_if_absent(
        session,
        user_id=user_id,
        offer_code=selected_template.offer_code,
        trigger_code=selected_template.trigger_code,
        priority=selected_template.priority,
        shown_at=now_utc,
        local_date_berlin=berlin_now(now_utc).date(),
        idempotency_key=idempotency_key,
    )
    if impression_id is None:
        replay = await OffersRepo.get_by_idempotency_key(
            session,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if replay is None:
            raise OfferLoggingError("offer impression logging failed")
        return selection_from_impression(replay, idempotent_replay=True)

    return selection_from_template(
        impression_id=impression_id,
        template=selected_template,
        idempotent_replay=False,
    )
