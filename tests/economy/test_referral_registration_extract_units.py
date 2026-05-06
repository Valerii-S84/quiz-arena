from __future__ import annotations

import pytest

from app.economy.referrals.service import registration


@pytest.mark.parametrize("start_payload", [None, "", "   ", "promo_ABC", "ref_ab", "ref_abc-123"])
def test_extract_referral_code_from_start_payload_rejects_invalid_values(
    start_payload: str | None,
) -> None:
    assert registration.extract_referral_code_from_start_payload(start_payload) is None


def test_extract_referral_code_from_start_payload_normalizes_valid_code() -> None:
    assert registration.extract_referral_code_from_start_payload("  ref_abC123  ") == "ABC123"
