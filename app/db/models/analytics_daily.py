from __future__ import annotations

from app.db.models.base import Base

from .analytics_daily_columns_core import AnalyticsDailyCoreMetricsMixin
from .analytics_daily_columns_duels import AnalyticsDailyDuelMetricsMixin
from .analytics_daily_constraints import ANALYTICS_DAILY_TABLE_ARGS


class AnalyticsDaily(
    AnalyticsDailyCoreMetricsMixin,
    AnalyticsDailyDuelMetricsMixin,
    Base,
):
    __tablename__ = "analytics_daily"
    __table_args__ = ANALYTICS_DAILY_TABLE_ARGS
