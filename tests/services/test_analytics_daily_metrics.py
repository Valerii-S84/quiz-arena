from app.services.analytics_daily_metrics import safe_rate


def test_safe_rate_returns_zero_for_empty_denominator() -> None:
    assert safe_rate(numerator=7, denominator=0) == 0.0


def test_safe_rate_caps_values_above_one() -> None:
    assert safe_rate(numerator=67, denominator=66) == 1.0


def test_safe_rate_preserves_normal_fraction() -> None:
    assert safe_rate(numerator=3, denominator=12) == 0.25
