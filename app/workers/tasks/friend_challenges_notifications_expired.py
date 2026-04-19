from __future__ import annotations

from app.workers.tasks.friend_challenges_notifications_expired_delivery import (
    deliver_expired_notice,
)
from app.workers.tasks.friend_challenges_notifications_expired_payloads import (
    expired_notice_context,
    expired_notice_result,
    expired_scores,
)


async def _send_expired_notice_item(
    *,
    bot,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[int, int, dict[str, object]] | None:
    scores = expired_scores(item)
    if scores is None:
        return None
    creator_score, opponent_score = scores
    challenge_id, status, previous_status, creator_chat, opponent_chat = expired_notice_context(
        item=item,
        telegram_targets=telegram_targets,
    )
    sent_to, failed_to = await deliver_expired_notice(
        bot=bot,
        challenge_id=challenge_id,
        creator_chat=creator_chat,
        opponent_chat=opponent_chat,
        creator_score=creator_score,
        opponent_score=opponent_score,
        status=status,
        previous_status=previous_status,
        has_opponent=isinstance(item["opponent_user_id"], int),
    )
    return expired_notice_result(
        challenge_id=challenge_id,
        status=status,
        previous_status=previous_status,
        sent_to=sent_to,
        failed_to=failed_to,
        creator_score=creator_score,
        opponent_score=opponent_score,
    )


async def send_expired_notices(
    *,
    bot,
    expired_items: list[dict[str, object]],
    telegram_targets: dict[int, int],
) -> tuple[int, int, list[dict[str, object]]]:
    expired_notices_sent = 0
    expired_notices_failed = 0
    expired_notice_events: list[dict[str, object]] = []
    for item in expired_items:
        notice_result = await _send_expired_notice_item(
            bot=bot,
            item=item,
            telegram_targets=telegram_targets,
        )
        if notice_result is None:
            continue
        sent_to, failed_to, event = notice_result
        expired_notices_sent += sent_to
        expired_notices_failed += failed_to
        expired_notice_events.append(event)
    return expired_notices_sent, expired_notices_failed, expired_notice_events
