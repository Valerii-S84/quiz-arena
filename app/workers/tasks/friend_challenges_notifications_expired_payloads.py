from __future__ import annotations


def expired_notice_targets(
    *,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[int | None, int | None]:
    creator_user_id = item["creator_user_id"]
    opponent_user_id = item["opponent_user_id"]
    creator_chat = (
        telegram_targets.get(creator_user_id) if isinstance(creator_user_id, int) else None
    )
    opponent_chat = (
        telegram_targets.get(opponent_user_id) if isinstance(opponent_user_id, int) else None
    )
    return creator_chat, opponent_chat


def expired_notice_result(
    *,
    challenge_id: str,
    status: str,
    previous_status: str,
    sent_to: int,
    failed_to: int,
    creator_score: int,
    opponent_score: int,
) -> tuple[int, int, dict[str, object]]:
    return (
        sent_to,
        failed_to,
        {
            "challenge_id": challenge_id,
            "status": status,
            "previous_status": previous_status,
            "sent_to": sent_to,
            "failed_to": failed_to,
            "creator_score": creator_score,
            "opponent_score": opponent_score,
        },
    )


def expired_scores(item: dict[str, object]) -> tuple[int, int] | None:
    creator_score = item["creator_score"]
    opponent_score = item["opponent_score"]
    if not isinstance(creator_score, int) or not isinstance(opponent_score, int):
        return None
    return creator_score, opponent_score


def expired_notice_context(
    *,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[str, str, str, int | None, int | None]:
    challenge_id = str(item["challenge_id"])
    status = str(item.get("status") or "")
    previous_status = str(item.get("previous_status") or "")
    creator_chat, opponent_chat = expired_notice_targets(
        item=item,
        telegram_targets=telegram_targets,
    )
    return challenge_id, status, previous_status, creator_chat, opponent_chat
