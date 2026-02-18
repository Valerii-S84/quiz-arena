from __future__ import annotations

import pytest

from app.core.referral_codes import ALPHABET, generate_referral_code


def test_generate_referral_code_length_and_charset() -> None:
    code = generate_referral_code(8)
    assert len(code) == 8
    assert set(code).issubset(set(ALPHABET))


def test_generate_referral_code_rejects_non_positive_length() -> None:
    with pytest.raises(ValueError):
        generate_referral_code(0)
