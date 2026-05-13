from __future__ import annotations

from uuid import UUID

from app.game.arena_duels.types import ArenaBeatenNotification


def notification_payload(notification: ArenaBeatenNotification) -> dict[str, object]:
    return {
        "arena_duel_id": str(notification.arena_duel_id),
        "previous_best_attempt_id": str(notification.previous_best_attempt_id),
        "previous_best_user_id": notification.previous_best_user_id,
        "previous_best_score": notification.previous_best_score,
        "previous_best_time_ms": notification.previous_best_time_ms,
        "new_best_attempt_id": str(notification.new_best_attempt_id),
        "new_best_user_id": notification.new_best_user_id,
        "new_best_score": notification.new_best_score,
        "new_best_time_ms": notification.new_best_time_ms,
        "notification_type": notification.notification_type,
    }


def notification_from_payload(payload: dict[str, object]) -> ArenaBeatenNotification:
    return ArenaBeatenNotification(
        arena_duel_id=UUID(str(payload["arena_duel_id"])),
        previous_best_attempt_id=UUID(str(payload["previous_best_attempt_id"])),
        previous_best_user_id=payload_int(payload, "previous_best_user_id"),
        previous_best_score=payload_int(payload, "previous_best_score"),
        previous_best_time_ms=payload_int(payload, "previous_best_time_ms"),
        new_best_attempt_id=UUID(str(payload["new_best_attempt_id"])),
        new_best_user_id=payload_int(payload, "new_best_user_id"),
        new_best_score=payload_int(payload, "new_best_score"),
        new_best_time_ms=payload_int(payload, "new_best_time_ms"),
        notification_type=str(payload["notification_type"]),
    )


def payload_int(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"Invalid arena notification payload field: {key}")
