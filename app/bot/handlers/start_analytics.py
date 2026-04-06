from __future__ import annotations

from app.bot.handlers.start_parsing import (
    _extract_duel_challenge_id,
    _extract_friend_challenge_token,
    _extract_tournament_invite_code,
)


def classify_start_source(start_payload: str | None) -> str:
    if not start_payload:
        return "direct"
    if start_payload.startswith("site_"):
        return start_payload
    if start_payload.startswith("ref_"):
        return "referral"
    if _extract_friend_challenge_token(start_payload) is not None:
        return "friend_challenge"
    if _extract_duel_challenge_id(start_payload) is not None:
        return "duel"
    if _extract_tournament_invite_code(start_payload) is not None:
        return "tournament"
    return "payload"


def build_start_event_payload(start_payload: str | None) -> dict[str, object]:
    payload: dict[str, object] = {"start_source": classify_start_source(start_payload)}
    if start_payload is not None:
        payload["start_payload"] = start_payload
    return payload
