from __future__ import annotations

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
ANALYTICS_DAILY_EVENT_TYPES = (
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
)


def duel_funnel_counts(event_counts: dict[str, int]) -> dict[str, int]:
    return {
        field_name: event_counts.get(event_type, 0)
        for event_type, field_name in DUEL_FUNNEL_EVENT_FIELDS
    }
