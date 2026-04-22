from __future__ import annotations

from datetime import timedelta

from app.economy.offers.constants import (
    BLOCKING_MODAL_COOLDOWN,
    MONETIZATION_IMPRESSIONS_PER_DAY_CAP,
    OFFER_MUTE_WINDOW,
    OFFER_REPEAT_COOLDOWN,
)


def test_offer_caps_match_default_configuration() -> None:
    assert BLOCKING_MODAL_COOLDOWN == timedelta(hours=6)
    assert MONETIZATION_IMPRESSIONS_PER_DAY_CAP == 3
    assert OFFER_REPEAT_COOLDOWN == timedelta(hours=24)
    assert OFFER_MUTE_WINDOW == timedelta(hours=72)
