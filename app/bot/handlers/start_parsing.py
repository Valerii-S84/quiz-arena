from __future__ import annotations

import re

START_PAYLOAD_RE = re.compile(r"^/start(?:@\w+)?(?:\s+(.+))?$")
START_FRIEND_PAYLOAD_RE = re.compile(r"^fc_([a-f0-9]{32})$", re.IGNORECASE)


def _extract_start_payload(text: str | None) -> str | None:
    if not text:
        return None
    matched = START_PAYLOAD_RE.match(text.strip())
    if matched is None:
        return None
    payload = matched.group(1)
    return payload.strip() if payload else None


def _extract_friend_challenge_token(start_payload: str | None) -> str | None:
    if not start_payload:
        return None
    matched = START_FRIEND_PAYLOAD_RE.fullmatch(start_payload.strip())
    if matched is None:
        return None
    return matched.group(1).lower()
