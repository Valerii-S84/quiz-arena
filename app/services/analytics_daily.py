from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.analytics_repo import AnalyticsDailyUpsert, AnalyticsRepo
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.game.arena_duels.analytics import (
    ARENA_EVENT_ARENA_DUEL_ACCEPTED,
    ARENA_EVENT_ARENA_DUEL_COMPLETED,
    ARENA_EVENT_ARENA_DUEL_CREATED,
    ARENA_EVENT_ARENA_DUEL_PUBLISHED,
    ARENA_EVENT_ARENA_DUEL_STARTED,
    ARENA_EVENT_ARENA_OPENED,
    ARENA_EVENT_ARENA_RESULT_SHOWN,
    ARENA_EVENT_ARENA_REVANCHE_CLICKED,
    ARENA_EVENT_DUEL_LIMIT_HIT,
    ARENA_EVENT_DUEL_MENU_OPENED,
    ARENA_EVENT_DUEL_MODE_SELECTED,
    ARENA_EVENT_DUEL_PAYWALL_SHOWN,
    ARENA_EVENT_DUEL_TICKET_CLICKED,
    ARENA_EVENT_FRIEND_DUEL_COMPLETED,
    ARENA_EVENT_FRIEND_DUEL_CREATED,
    ARENA_EVENT_FRIEND_DUEL_JOINED,
    ARENA_EVENT_FRIEND_DUEL_OPENED,
    ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA,
    ARENA_EVENT_FRIEND_DUEL_REVANCHE_CLICKED,
    ARENA_EVENT_FRIEND_DUEL_SHARE_CLICKED,
    ARENA_EVENT_FRIEND_DUEL_STARTED,
    ARENA_EVENT_PREMIUM_WEEK_CLICKED,
)

ENERGY_ZERO_EVENT = "gameplay_energy_zero"
STREAK_LOST_EVENT = "streak_lost"
REFERRAL_REWARD_MILESTONE_EVENT = "referral_reward_milestone_available"
REFERRAL_REWARD_GRANTED_EVENT = "referral_reward_granted"
PURCHASE_INIT_EVENT = "purchase_init_created"
PURCHASE_INVOICE_SENT_EVENT = "purchase_invoice_sent"
PURCHASE_PRECHECKOUT_OK_EVENT = "purchase_precheckout_ok"
PURCHASE_PAID_UNCREDITED_EVENT = "purchase_paid_uncredited"
PURCHASE_CREDITED_EVENT = "purchase_credited"
ARENA_RESULT_BEATEN_NOTIFICATION_SENT_EVENT = "arena_result_beaten_notification_sent"

DUEL_FUNNEL_EVENT_FIELDS = (
    (ARENA_EVENT_DUEL_MENU_OPENED, "duel_menu_opened_events_total"),
    (ARENA_EVENT_DUEL_MODE_SELECTED, "duel_mode_selected_events_total"),
    (ARENA_EVENT_ARENA_OPENED, "arena_opened_events_total"),
    (ARENA_EVENT_ARENA_DUEL_CREATED, "arena_duel_created_events_total"),
    (ARENA_EVENT_ARENA_DUEL_STARTED, "arena_duel_started_events_total"),
    (ARENA_EVENT_ARENA_DUEL_COMPLETED, "arena_duel_completed_events_total"),
    (ARENA_EVENT_ARENA_DUEL_PUBLISHED, "arena_duel_published_events_total"),
    (ARENA_EVENT_ARENA_DUEL_ACCEPTED, "arena_duel_accepted_events_total"),
    (ARENA_EVENT_ARENA_RESULT_SHOWN, "arena_result_shown_events_total"),
    (
        ARENA_RESULT_BEATEN_NOTIFICATION_SENT_EVENT,
        "arena_result_beaten_notification_sent_events_total",
    ),
    (ARENA_EVENT_ARENA_REVANCHE_CLICKED, "arena_revanche_clicked_events_total"),
    (ARENA_EVENT_FRIEND_DUEL_OPENED, "friend_duel_opened_events_total"),
    (ARENA_EVENT_FRIEND_DUEL_CREATED, "friend_duel_created_events_total"),
    (ARENA_EVENT_FRIEND_DUEL_SHARE_CLICKED, "friend_duel_share_clicked_events_total"),
    (ARENA_EVENT_FRIEND_DUEL_JOINED, "friend_duel_joined_events_total"),
    (ARENA_EVENT_FRIEND_DUEL_STARTED, "friend_duel_started_events_total"),
    (ARENA_EVENT_FRIEND_DUEL_COMPLETED, "friend_duel_completed_events_total"),
    (
        ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA,
        "friend_duel_published_to_arena_events_total",
    ),
    (ARENA_EVENT_FRIEND_DUEL_REVANCHE_CLICKED, "friend_duel_revanche_clicked_events_total"),
    (ARENA_EVENT_DUEL_LIMIT_HIT, "duel_limit_hit_events_total"),
    (ARENA_EVENT_DUEL_PAYWALL_SHOWN, "duel_paywall_shown_events_total"),
    (ARENA_EVENT_DUEL_TICKET_CLICKED, "duel_ticket_clicked_events_total"),
    (ARENA_EVENT_PREMIUM_WEEK_CLICKED, "premium_week_clicked_events_total"),
)
DUEL_FUNNEL_EVENTS = tuple(event_type for event_type, _field_name in DUEL_FUNNEL_EVENT_FIELDS)


@dataclass(frozen=True, slots=True)
class AnalyticsDailySnapshot:
    row: AnalyticsDailyUpsert
    day_start_utc: datetime
    day_end_utc: datetime


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _berlin_day_bounds_utc(local_date_berlin: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(BERLIN_TIMEZONE)
    day_start_local = datetime.combine(local_date_berlin, time.min, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    return (
        day_start_local.astimezone(ZoneInfo("UTC")),
        day_end_local.astimezone(ZoneInfo("UTC")),
    )


def _duel_funnel_counts(event_counts: dict[str, int]) -> dict[str, int]:
    return {
        field_name: event_counts.get(event_type, 0)
        for event_type, field_name in DUEL_FUNNEL_EVENT_FIELDS
    }


async def build_daily_snapshot(
    session: AsyncSession,
    *,
    local_date_berlin: date,
    now_utc: datetime,
) -> AnalyticsDailySnapshot:
    day_start_utc, day_end_utc = _berlin_day_bounds_utc(local_date_berlin)
    wau_start_utc = day_end_utc - timedelta(days=7)
    mau_start_utc = day_end_utc - timedelta(days=30)

    dau = await AnalyticsRepo.count_distinct_active_users_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    wau = await AnalyticsRepo.count_distinct_active_users_between(
        session,
        from_utc=wau_start_utc,
        to_utc=day_end_utc,
    )
    mau = await AnalyticsRepo.count_distinct_active_users_between(
        session,
        from_utc=mau_start_utc,
        to_utc=day_end_utc,
    )

    purchases_credited_total = await AnalyticsRepo.count_credited_purchases_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    purchasers_total = await AnalyticsRepo.count_distinct_credited_purchasers_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    promo_to_paid_conversions_total = await AnalyticsRepo.count_promo_to_paid_conversions_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )

    promo_redemptions_total = await AnalyticsRepo.count_promo_redemptions_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    promo_redemptions_applied_total = await AnalyticsRepo.count_applied_promo_redemptions_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )

    quiz_sessions_started_total = await AnalyticsRepo.count_quiz_sessions_started_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    quiz_sessions_completed_total = await AnalyticsRepo.count_quiz_sessions_completed_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )

    event_counts = await AnalyticsRepo.count_events_by_type_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
        event_types=(
            ENERGY_ZERO_EVENT,
            STREAK_LOST_EVENT,
            REFERRAL_REWARD_MILESTONE_EVENT,
            REFERRAL_REWARD_GRANTED_EVENT,
            PURCHASE_INIT_EVENT,
            PURCHASE_INVOICE_SENT_EVENT,
            PURCHASE_PRECHECKOUT_OK_EVENT,
            PURCHASE_PAID_UNCREDITED_EVENT,
            PURCHASE_CREDITED_EVENT,
            *DUEL_FUNNEL_EVENTS,
        ),
    )

    return AnalyticsDailySnapshot(
        row=AnalyticsDailyUpsert(
            local_date_berlin=local_date_berlin,
            dau=dau,
            wau=wau,
            mau=mau,
            purchases_credited_total=purchases_credited_total,
            purchasers_total=purchasers_total,
            purchase_rate=_safe_rate(numerator=purchasers_total, denominator=dau),
            promo_redemptions_total=promo_redemptions_total,
            promo_redemptions_applied_total=promo_redemptions_applied_total,
            promo_redemption_rate=_safe_rate(
                numerator=promo_redemptions_applied_total,
                denominator=promo_redemptions_total,
            ),
            promo_to_paid_conversions_total=promo_to_paid_conversions_total,
            quiz_sessions_started_total=quiz_sessions_started_total,
            quiz_sessions_completed_total=quiz_sessions_completed_total,
            gameplay_completion_rate=_safe_rate(
                numerator=quiz_sessions_completed_total,
                denominator=quiz_sessions_started_total,
            ),
            energy_zero_events_total=event_counts.get(ENERGY_ZERO_EVENT, 0),
            streak_lost_events_total=event_counts.get(STREAK_LOST_EVENT, 0),
            referral_reward_milestone_events_total=event_counts.get(
                REFERRAL_REWARD_MILESTONE_EVENT, 0
            ),
            referral_reward_granted_events_total=event_counts.get(REFERRAL_REWARD_GRANTED_EVENT, 0),
            purchase_init_events_total=event_counts.get(PURCHASE_INIT_EVENT, 0),
            purchase_invoice_sent_events_total=event_counts.get(PURCHASE_INVOICE_SENT_EVENT, 0),
            purchase_precheckout_ok_events_total=event_counts.get(PURCHASE_PRECHECKOUT_OK_EVENT, 0),
            purchase_paid_uncredited_events_total=event_counts.get(
                PURCHASE_PAID_UNCREDITED_EVENT, 0
            ),
            purchase_credited_events_total=event_counts.get(PURCHASE_CREDITED_EVENT, 0),
            **_duel_funnel_counts(event_counts),
            calculated_at=now_utc,
        ),
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )
