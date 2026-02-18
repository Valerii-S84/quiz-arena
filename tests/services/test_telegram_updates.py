from app.services.telegram_updates import extract_update_id, is_valid_webhook_secret


def test_extract_update_id_returns_int_for_valid_payload() -> None:
    assert extract_update_id({"update_id": 42, "message": {}}) == 42


def test_extract_update_id_returns_none_for_invalid_payload() -> None:
    assert extract_update_id({"update_id": "42"}) is None
    assert extract_update_id({"message": {}}) is None
    assert extract_update_id("not-a-dict") is None


def test_is_valid_webhook_secret_accepts_exact_match() -> None:
    assert is_valid_webhook_secret(expected_secret="abc123", received_secret="abc123") is True


def test_is_valid_webhook_secret_rejects_missing_or_mismatch() -> None:
    assert is_valid_webhook_secret(expected_secret="abc123", received_secret=None) is False
    assert is_valid_webhook_secret(expected_secret="abc123", received_secret="wrong") is False
