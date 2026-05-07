from __future__ import annotations

from sqlalchemy import Integer, text
from sqlalchemy.orm import Mapped, mapped_column


def _int_metric() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default=text("0"))


class AnalyticsDailyDuelMetricsMixin:
    duel_menu_opened_events_total: Mapped[int] = _int_metric()
    duel_mode_selected_events_total: Mapped[int] = _int_metric()
    arena_opened_events_total: Mapped[int] = _int_metric()
    arena_duel_created_events_total: Mapped[int] = _int_metric()
    arena_duel_started_events_total: Mapped[int] = _int_metric()
    arena_duel_completed_events_total: Mapped[int] = _int_metric()
    arena_duel_published_events_total: Mapped[int] = _int_metric()
    arena_duel_accepted_events_total: Mapped[int] = _int_metric()
    arena_result_shown_events_total: Mapped[int] = _int_metric()
    arena_result_beaten_notification_sent_events_total: Mapped[int] = _int_metric()
    arena_revanche_clicked_events_total: Mapped[int] = _int_metric()
    friend_duel_opened_events_total: Mapped[int] = _int_metric()
    friend_duel_created_events_total: Mapped[int] = _int_metric()
    friend_duel_share_clicked_events_total: Mapped[int] = _int_metric()
    friend_duel_joined_events_total: Mapped[int] = _int_metric()
    friend_duel_started_events_total: Mapped[int] = _int_metric()
    friend_duel_completed_events_total: Mapped[int] = _int_metric()
    friend_duel_published_to_arena_events_total: Mapped[int] = _int_metric()
    friend_duel_revanche_clicked_events_total: Mapped[int] = _int_metric()
    duel_limit_hit_events_total: Mapped[int] = _int_metric()
    duel_paywall_shown_events_total: Mapped[int] = _int_metric()
    duel_ticket_clicked_events_total: Mapped[int] = _int_metric()
    premium_week_clicked_events_total: Mapped[int] = _int_metric()
