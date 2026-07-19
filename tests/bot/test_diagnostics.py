from __future__ import annotations

from app.bot.diagnostic_sanitizers import payload_metadata, scalar_metadata


def test_payload_metadata_masks_raw_text() -> None:
    metadata = payload_metadata("/promo SECRET-CODE")

    assert metadata == {
        "present": True,
        "length": 18,
        "starts_with_slash": True,
    }
    assert "SECRET-CODE" not in repr(metadata)


def test_scalar_metadata_masks_string_values() -> None:
    metadata = scalar_metadata("redemption-token")

    assert metadata == {"type": "str", "length": 16}
    assert "redemption-token" not in repr(metadata)
