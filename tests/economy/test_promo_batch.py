from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.economy.promo.batch import generate_raw_codes, parse_utc_datetime


def test_generate_raw_codes_returns_unique_codes_with_prefix() -> None:
    codes = generate_raw_codes(count=5, token_length=6, prefix="WELCOME-")
    assert len(codes) == 5
    assert len(set(codes)) == 5
    assert all(code.startswith("WELCOME-") for code in codes)


def test_generate_raw_codes_rejects_invalid_count() -> None:
    with pytest.raises(ValueError):
        generate_raw_codes(count=0)


def test_parse_utc_datetime_supports_naive_and_aware() -> None:
    naive = parse_utc_datetime("2026-02-18T12:30:00")
    aware = parse_utc_datetime("2026-02-18T12:30:00+02:00")

    assert naive == datetime(2026, 2, 18, 12, 30, tzinfo=timezone.utc)
    assert aware == datetime(2026, 2, 18, 10, 30, tzinfo=timezone.utc)
