from __future__ import annotations

import base64
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_NONCE_LENGTH = 12
_KEY_LENGTH = 32


def _decode_encryption_key(raw_key: str) -> bytes:
    normalized_key = raw_key.strip()
    if not normalized_key:
        raise ValueError("PROMO_ENCRYPTION_KEY is empty")

    padding = "=" * (-len(normalized_key) % 4)
    decoded_key = base64.urlsafe_b64decode(f"{normalized_key}{padding}".encode("ascii"))
    if len(decoded_key) != _KEY_LENGTH:
        raise ValueError("PROMO_ENCRYPTION_KEY must decode to 32 bytes")
    return decoded_key


def encrypt_promo_code(raw_code: str) -> bytes:
    key = _decode_encryption_key(get_settings().promo_encryption_key)
    nonce = secrets.token_bytes(_NONCE_LENGTH)
    ciphertext = AESGCM(key).encrypt(nonce, raw_code.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_promo_code(code_encrypted: bytes) -> str:
    if len(code_encrypted) <= _NONCE_LENGTH:
        raise ValueError("Encrypted promo code payload is invalid")

    key = _decode_encryption_key(get_settings().promo_encryption_key)
    nonce = code_encrypted[:_NONCE_LENGTH]
    ciphertext = code_encrypted[_NONCE_LENGTH:]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
