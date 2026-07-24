from __future__ import annotations


def phase_repair_target_id(
    *,
    user_id: int,
    standings_message_id: int | None,
    status: str,
    current_round: int,
    flow: str,
) -> str:
    content_version = _content_version(status=status, current_round=current_round, flow=flow)
    operation = "send" if standings_message_id is None else f"edit:{standings_message_id}"
    return f"{user_id}:phase:{content_version}:{operation}"


def phase_repair_match_id(target_id: str) -> str:
    normalized = target_id
    for operation_marker in (":fallback_send_after_edit:", ":edit:"):
        if operation_marker in normalized:
            normalized = normalized.rsplit(operation_marker, 1)[0]
            break
    else:
        if normalized.endswith(":send"):
            normalized = normalized[: -len(":send")]
    if ":c:" in normalized:
        normalized = normalized.split(":c:", 1)[0]
    return normalized


def _content_version(*, status: str, current_round: int, flow: str) -> str:
    normalized_status = status.lower()
    if normalized_status == "completed":
        return "status:completed"
    if flow == "daily_cup_round_messaging" and normalized_status == "canceled":
        return "status:canceled"
    return f"round:{max(1, current_round)}:status:{normalized_status}"


__all__ = ["phase_repair_match_id", "phase_repair_target_id"]
