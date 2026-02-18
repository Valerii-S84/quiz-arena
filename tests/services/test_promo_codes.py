from app.services.promo_codes import hash_promo_code, normalize_promo_code


def test_normalize_promo_code_removes_spaces_and_hyphens() -> None:
    assert normalize_promo_code("  will-kommen  50  ") == "WILLKOMMEN50"


def test_hash_promo_code_is_deterministic_and_pepper_sensitive() -> None:
    normalized = "WILLKOMMEN50"
    hash_a = hash_promo_code(normalized_code=normalized, pepper="pepper-a")
    hash_b = hash_promo_code(normalized_code=normalized, pepper="pepper-a")
    hash_c = hash_promo_code(normalized_code=normalized, pepper="pepper-b")

    assert hash_a == hash_b
    assert hash_a != hash_c
