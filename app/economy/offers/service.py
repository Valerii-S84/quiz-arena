from __future__ import annotations

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.offers_impressions import OfferImpression
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.offers_repo import OffersRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.energy.constants import BERLIN_TIMEZONE, FREE_ENERGY_START
from app.economy.offers.constants import (
    BLOCKING_MODAL_COOLDOWN,
    BLOCKING_OFFER_CODES,
    COMEBACK_WINDOW_DAYS,
    ENERGY10_SECOND_BUY_WINDOW,
    MEGA_THIRD_BUY_WINDOW,
    MONETIZATION_IMPRESSIONS_PER_DAY_CAP,
    MONTH_EXPIRING_WINDOW,
    OFFER_MUTE_WINDOW,
    OFFER_NOT_SHOW_DISMISS_REASON,
    OFFER_REPEAT_COOLDOWN,
    OFFER_TEMPLATES,
    STARTER_EXPIRED_WINDOW,
    TRG_COMEBACK_3D,
    TRG_ENERGY10_SECOND_BUY,
    TRG_ENERGY_LOW,
    TRG_ENERGY_ZERO,
    TRG_LOCKED_MODE_CLICK,
    TRG_MEGA_THIRD_BUY,
    TRG_MONTH_EXPIRING,
    TRG_STARTER_EXPIRED,
    TRG_STREAK_GT7,
    TRG_STREAK_MILESTONE_30,
    TRG_STREAK_RISK_22,
    TRG_WEEKEND_FLASH,
    TRIGGER_RESOLUTION_ORDER,
)
from app.economy.offers.types import OfferSelection, OfferTemplate


class OfferLoggingError(Exception):
    pass


class OfferService:
    @staticmethod
    def _berlin_now(now_utc: datetime) -> datetime:
        return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE))

    @staticmethod
    def _is_weekend_flash_window(local_now: datetime) -> bool:
        weekday = local_now.weekday()  # Monday=0 ... Sunday=6
        if weekday == 4:
            return local_now.hour >= 18
        return weekday in {5, 6}

    @staticmethod
    def _selection_from_template(
        *,
        impression_id: int,
        template: OfferTemplate,
        idempotent_replay: bool,
    ) -> OfferSelection:
        return OfferSelection(
            impression_id=impression_id,
            offer_code=template.offer_code,
            trigger_code=template.trigger_code,
            priority=template.priority,
            text_key=template.text_key,
            cta_product_codes=template.cta_product_codes,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _selection_from_impression(
        impression: OfferImpression,
        *,
        idempotent_replay: bool,
    ) -> OfferSelection | None:
        template = OFFER_TEMPLATES.get(impression.trigger_code)
        if template is None:
            return None

        return OfferService._selection_from_template(
            impression_id=impression.id,
            template=template,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _is_offer_muted(
        *,
        offer_code: str,
        recent_impressions: list[OfferImpression],
        now_utc: datetime,
    ) -> bool:
        mute_threshold = now_utc - OFFER_MUTE_WINDOW
        for impression in recent_impressions:
            if impression.offer_code != offer_code:
                continue
            if impression.dismiss_reason != OFFER_NOT_SHOW_DISMISS_REASON:
                continue
            if impression.clicked_at is None:
                continue
            if impression.clicked_at >= mute_threshold:
                return True
        return False

    @staticmethod
    def _was_offer_shown_recently(
        *,
        offer_code: str,
        recent_impressions: list[OfferImpression],
        now_utc: datetime,
    ) -> bool:
        repeat_threshold = now_utc - OFFER_REPEAT_COOLDOWN
        for impression in recent_impressions:
            if impression.offer_code == offer_code and impression.shown_at >= repeat_threshold:
                return True
        return False

    @staticmethod
    def _has_recent_blocking_modal(
        *,
        recent_impressions: list[OfferImpression],
        now_utc: datetime,
    ) -> bool:
        threshold = now_utc - BLOCKING_MODAL_COOLDOWN
        for impression in recent_impressions:
            if impression.offer_code in BLOCKING_OFFER_CODES and impression.shown_at >= threshold:
                return True
        return False

    @staticmethod
    async def _build_trigger_codes(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
        trigger_event: str | None,
    ) -> set[str]:
        trigger_codes: set[str] = set()
        berlin_now = OfferService._berlin_now(now_utc)
        berlin_today = berlin_now.date()

        energy_state = await EnergyRepo.get_by_user_id(session, user_id)
        total_energy = (
            FREE_ENERGY_START
            if energy_state is None
            else max(0, int(energy_state.free_energy) + int(energy_state.paid_energy))
        )

        streak_state = await StreakRepo.get_by_user_id(session, user_id)
        current_streak = 0 if streak_state is None else int(streak_state.current_streak)
        today_status = "NO_ACTIVITY" if streak_state is None else streak_state.today_status
        last_activity_local_date: date | None = None if streak_state is None else streak_state.last_activity_local_date

        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)

        if not premium_active and total_energy == 0:
            trigger_codes.add(TRG_ENERGY_ZERO)
        if not premium_active and 1 <= total_energy <= 3:
            trigger_codes.add(TRG_ENERGY_LOW)

        energy10_count = await PurchasesRepo.count_paid_product_since(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            since_utc=now_utc - ENERGY10_SECOND_BUY_WINDOW,
        )
        if not premium_active and energy10_count >= 2:
            trigger_codes.add(TRG_ENERGY10_SECOND_BUY)

        if trigger_event == TRG_LOCKED_MODE_CLICK and not premium_active:
            trigger_codes.add(TRG_LOCKED_MODE_CLICK)

        if current_streak > 7:
            trigger_codes.add(TRG_STREAK_GT7)
        if current_streak > 14 and berlin_now.hour >= 22 and today_status == "NO_ACTIVITY":
            trigger_codes.add(TRG_STREAK_RISK_22)
        if current_streak >= 30:
            trigger_codes.add(TRG_STREAK_MILESTONE_30)

        if last_activity_local_date is not None:
            if (berlin_today - last_activity_local_date).days >= COMEBACK_WINDOW_DAYS:
                trigger_codes.add(TRG_COMEBACK_3D)

        mega_count = await PurchasesRepo.count_paid_product_since(
            session,
            user_id=user_id,
            product_code="MEGA_PACK_15",
            since_utc=now_utc - MEGA_THIRD_BUY_WINDOW,
        )
        if not premium_active and mega_count >= 3:
            trigger_codes.add(TRG_MEGA_THIRD_BUY)

        starter_expired_recently = await EntitlementsRepo.has_recently_ended_premium_scope(
            session,
            user_id=user_id,
            scope="PREMIUM_STARTER",
            since_utc=now_utc - STARTER_EXPIRED_WINDOW,
            until_utc=now_utc,
        )
        if not premium_active and starter_expired_recently:
            trigger_codes.add(TRG_STARTER_EXPIRED)

        month_expiring = await EntitlementsRepo.has_active_premium_scope_ending_within(
            session,
            user_id=user_id,
            scope="PREMIUM_MONTH",
            now_utc=now_utc,
            until_utc=now_utc + MONTH_EXPIRING_WINDOW,
        )
        if month_expiring:
            trigger_codes.add(TRG_MONTH_EXPIRING)

        if OfferService._is_weekend_flash_window(berlin_now):
            trigger_codes.add(TRG_WEEKEND_FLASH)

        return trigger_codes

    @staticmethod
    async def _select_template_with_caps(
        session: AsyncSession,
        *,
        user_id: int,
        trigger_codes: set[str],
        now_utc: datetime,
    ) -> OfferTemplate | None:
        if not trigger_codes:
            return None

        berlin_today = OfferService._berlin_now(now_utc).date()
        recent_impressions = await OffersRepo.list_for_user_since(
            session,
            user_id=user_id,
            shown_since_utc=now_utc - OFFER_MUTE_WINDOW,
        )

        daily_impressions = sum(
            1 for impression in recent_impressions if impression.local_date_berlin == berlin_today
        )
        if daily_impressions >= MONETIZATION_IMPRESSIONS_PER_DAY_CAP:
            return None

        blocking_recently_shown = OfferService._has_recent_blocking_modal(
            recent_impressions=recent_impressions,
            now_utc=now_utc,
        )

        order_map = {
            trigger_code: index for index, trigger_code in enumerate(TRIGGER_RESOLUTION_ORDER)
        }
        ordered_templates = sorted(
            (OFFER_TEMPLATES[trigger_code] for trigger_code in trigger_codes),
            key=lambda template: (
                -template.priority,
                order_map.get(template.trigger_code, len(order_map)),
            ),
        )

        for template in ordered_templates:
            if template.blocking_modal and blocking_recently_shown:
                continue
            if OfferService._was_offer_shown_recently(
                offer_code=template.offer_code,
                recent_impressions=recent_impressions,
                now_utc=now_utc,
            ):
                continue
            if OfferService._is_offer_muted(
                offer_code=template.offer_code,
                recent_impressions=recent_impressions,
                now_utc=now_utc,
            ):
                continue
            return template

        return None

    @staticmethod
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
            return OfferService._selection_from_impression(existing, idempotent_replay=True)

        trigger_codes = await OfferService._build_trigger_codes(
            session,
            user_id=user_id,
            now_utc=now_utc,
            trigger_event=trigger_event,
        )
        if not trigger_codes:
            return None

        selected_template = await OfferService._select_template_with_caps(
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
            local_date_berlin=OfferService._berlin_now(now_utc).date(),
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
            return OfferService._selection_from_impression(replay, idempotent_replay=True)

        return OfferService._selection_from_template(
            impression_id=impression_id,
            template=selected_template,
            idempotent_replay=False,
        )

    @staticmethod
    async def dismiss_offer(
        session: AsyncSession,
        *,
        user_id: int,
        impression_id: int,
        now_utc: datetime,
    ) -> bool:
        return await OffersRepo.mark_dismissed(
            session,
            user_id=user_id,
            impression_id=impression_id,
            dismiss_reason=OFFER_NOT_SHOW_DISMISS_REASON,
            dismissed_at=now_utc,
        )

    @staticmethod
    async def mark_offer_clicked(
        session: AsyncSession,
        *,
        user_id: int,
        impression_id: int,
        clicked_at: datetime,
    ) -> bool:
        return await OffersRepo.mark_clicked(
            session,
            user_id=user_id,
            impression_id=impression_id,
            clicked_at=clicked_at,
        )

    @staticmethod
    async def mark_offer_converted_purchase(
        session: AsyncSession,
        *,
        user_id: int,
        impression_id: int,
        purchase_id: UUID,
    ) -> bool:
        return await OffersRepo.mark_converted_purchase(
            session,
            user_id=user_id,
            impression_id=impression_id,
            purchase_id=purchase_id,
        )
