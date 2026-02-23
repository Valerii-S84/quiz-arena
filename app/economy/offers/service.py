from __future__ import annotations

from app.economy.offers.actions import (
    dismiss_offer,
    mark_offer_clicked,
    mark_offer_converted_purchase,
)
from app.economy.offers.errors import OfferLoggingError
from app.economy.offers.evaluation import evaluate_and_log_offer
from app.economy.offers.muting import (
    has_recent_blocking_modal,
    is_offer_muted,
    was_offer_shown_recently,
)
from app.economy.offers.selection import selection_from_impression, selection_from_template
from app.economy.offers.template_selection import select_template_with_caps
from app.economy.offers.time_utils import berlin_now, is_weekend_flash_window
from app.economy.offers.triggers import build_trigger_codes


class OfferService:
    _berlin_now = staticmethod(berlin_now)
    _is_weekend_flash_window = staticmethod(is_weekend_flash_window)
    _selection_from_template = staticmethod(selection_from_template)
    _selection_from_impression = staticmethod(selection_from_impression)
    _is_offer_muted = staticmethod(is_offer_muted)
    _was_offer_shown_recently = staticmethod(was_offer_shown_recently)
    _has_recent_blocking_modal = staticmethod(has_recent_blocking_modal)
    _build_trigger_codes = staticmethod(build_trigger_codes)
    _select_template_with_caps = staticmethod(select_template_with_caps)
    evaluate_and_log_offer = staticmethod(evaluate_and_log_offer)
    dismiss_offer = staticmethod(dismiss_offer)
    mark_offer_clicked = staticmethod(mark_offer_clicked)
    mark_offer_converted_purchase = staticmethod(mark_offer_converted_purchase)


__all__ = ["OfferLoggingError", "OfferService"]
