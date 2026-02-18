from __future__ import annotations

from datetime import timedelta

from app.economy.offers.types import OfferTemplate

TRG_ENERGY_ZERO = "TRG_ENERGY_ZERO"
TRG_ENERGY_LOW = "TRG_ENERGY_LOW"
TRG_ENERGY10_SECOND_BUY = "TRG_ENERGY10_SECOND_BUY"
TRG_LOCKED_MODE_CLICK = "TRG_LOCKED_MODE_CLICK"
TRG_STREAK_GT7 = "TRG_STREAK_GT7"
TRG_STREAK_RISK_22 = "TRG_STREAK_RISK_22"
TRG_STREAK_MILESTONE_30 = "TRG_STREAK_MILESTONE_30"
TRG_COMEBACK_3D = "TRG_COMEBACK_3D"
TRG_MEGA_THIRD_BUY = "TRG_MEGA_THIRD_BUY"
TRG_STARTER_EXPIRED = "TRG_STARTER_EXPIRED"
TRG_MONTH_EXPIRING = "TRG_MONTH_EXPIRING"
TRG_WEEKEND_FLASH = "TRG_WEEKEND_FLASH"

TRIGGER_RESOLUTION_ORDER: tuple[str, ...] = (
    TRG_ENERGY_ZERO,
    TRG_STREAK_RISK_22,
    TRG_LOCKED_MODE_CLICK,
    TRG_STARTER_EXPIRED,
    TRG_COMEBACK_3D,
    TRG_ENERGY10_SECOND_BUY,
    TRG_MEGA_THIRD_BUY,
    TRG_MONTH_EXPIRING,
    TRG_ENERGY_LOW,
    TRG_STREAK_GT7,
    TRG_STREAK_MILESTONE_30,
    TRG_WEEKEND_FLASH,
)

OFFER_NOT_SHOW_DISMISS_REASON = "NOT_SHOW"

BLOCKING_MODAL_COOLDOWN = timedelta(hours=6)
MONETIZATION_IMPRESSIONS_PER_DAY_CAP = 3
OFFER_REPEAT_COOLDOWN = timedelta(hours=24)
OFFER_MUTE_WINDOW = timedelta(hours=72)

ENERGY10_SECOND_BUY_WINDOW = timedelta(days=7)
MEGA_THIRD_BUY_WINDOW = timedelta(days=14)
COMEBACK_WINDOW_DAYS = 3
STARTER_EXPIRED_WINDOW = timedelta(hours=48)
MONTH_EXPIRING_WINDOW = timedelta(hours=72)

OFFER_TEMPLATES: dict[str, OfferTemplate] = {
    TRG_ENERGY_ZERO: OfferTemplate(
        offer_code="OFFER_ENERGY_ZERO",
        trigger_code=TRG_ENERGY_ZERO,
        priority=100,
        text_key="msg.offer.energy.zero",
        cta_product_codes=("ENERGY_10", "MEGA_PACK_15", "PREMIUM_MONTH"),
        blocking_modal=True,
    ),
    TRG_ENERGY_LOW: OfferTemplate(
        offer_code="OFFER_ENERGY_LOW",
        trigger_code=TRG_ENERGY_LOW,
        priority=60,
        text_key="msg.offer.energy.low",
        cta_product_codes=("ENERGY_10",),
        blocking_modal=False,
    ),
    TRG_ENERGY10_SECOND_BUY: OfferTemplate(
        offer_code="OFFER_MEGA_AFTER_ENERGY",
        trigger_code=TRG_ENERGY10_SECOND_BUY,
        priority=80,
        text_key="msg.offer.mega.after_second_energy",
        cta_product_codes=("MEGA_PACK_15",),
        blocking_modal=True,
    ),
    TRG_LOCKED_MODE_CLICK: OfferTemplate(
        offer_code="OFFER_LOCKED_MODE_MEGA",
        trigger_code=TRG_LOCKED_MODE_CLICK,
        priority=90,
        text_key="msg.offer.locked.mode",
        cta_product_codes=("MEGA_PACK_15",),
        blocking_modal=True,
    ),
    TRG_STREAK_GT7: OfferTemplate(
        offer_code="OFFER_STREAK_GT7",
        trigger_code=TRG_STREAK_GT7,
        priority=50,
        text_key="msg.offer.streak.gt7",
        cta_product_codes=("MEGA_PACK_15",),
        blocking_modal=True,
    ),
    TRG_STREAK_RISK_22: OfferTemplate(
        offer_code="OFFER_STREAK_RISK",
        trigger_code=TRG_STREAK_RISK_22,
        priority=95,
        text_key="msg.offer.streak.risk",
        cta_product_codes=("STREAK_SAVER_20",),
        blocking_modal=True,
    ),
    TRG_STREAK_MILESTONE_30: OfferTemplate(
        offer_code="OFFER_STREAK_MILESTONE_30",
        trigger_code=TRG_STREAK_MILESTONE_30,
        priority=55,
        text_key="msg.offer.streak.milestone.30",
        cta_product_codes=("STREAK_SAVER_20", "PREMIUM_MONTH"),
        blocking_modal=True,
    ),
    TRG_COMEBACK_3D: OfferTemplate(
        offer_code="OFFER_COMEBACK_3D",
        trigger_code=TRG_COMEBACK_3D,
        priority=85,
        text_key="msg.offer.comeback",
        cta_product_codes=("MEGA_PACK_15",),
        blocking_modal=True,
    ),
    TRG_MEGA_THIRD_BUY: OfferTemplate(
        offer_code="OFFER_PREMIUM_STARTER",
        trigger_code=TRG_MEGA_THIRD_BUY,
        priority=88,
        text_key="msg.offer.mega.third.buy",
        cta_product_codes=("PREMIUM_STARTER",),
        blocking_modal=True,
    ),
    TRG_STARTER_EXPIRED: OfferTemplate(
        offer_code="OFFER_STARTER_TO_MONTH",
        trigger_code=TRG_STARTER_EXPIRED,
        priority=92,
        text_key="msg.offer.starter.to.month",
        cta_product_codes=("PREMIUM_MONTH",),
        blocking_modal=True,
    ),
    TRG_MONTH_EXPIRING: OfferTemplate(
        offer_code="OFFER_MONTH_TO_LONG",
        trigger_code=TRG_MONTH_EXPIRING,
        priority=70,
        text_key="msg.offer.month.to.season_year",
        cta_product_codes=("PREMIUM_SEASON", "PREMIUM_YEAR"),
        blocking_modal=True,
    ),
    TRG_WEEKEND_FLASH: OfferTemplate(
        offer_code="OFFER_WEEKEND_FLASH",
        trigger_code=TRG_WEEKEND_FLASH,
        priority=40,
        text_key="msg.offer.weekend.flash",
        cta_product_codes=("MEGA_PACK_15",),
        blocking_modal=False,
    ),
}

BLOCKING_OFFER_CODES: set[str] = {
    template.offer_code for template in OFFER_TEMPLATES.values() if template.blocking_modal
}
