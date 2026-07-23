from __future__ import annotations

from app.game.arena_duels.types import ArenaBeatenNotification
from app.workers.tasks.arena_duels_notification_content import (
    build_arena_beaten_notification_keyboard,
    build_notification_text,
    classify_beaten_notification_action_mode,
    format_user_label,
)


async def send_notification_message(
    bot,
    notification: ArenaBeatenNotification,
    previous_user,
    new_best_user,
) -> None:
    challenger_label = format_user_label(
        username=getattr(new_best_user, "username", None),
        first_name=getattr(new_best_user, "first_name", None),
        fallback=f"Spieler #{notification.new_best_user_id}",
    )
    await bot.send_message(
        chat_id=int(previous_user.telegram_user_id),
        text=build_notification_text(
            notification=notification,
            challenger_label=challenger_label,
        ),
        reply_markup=build_arena_beaten_notification_keyboard(
            source_attempt_id=str(notification.new_best_attempt_id),
            action_mode=classify_beaten_notification_action_mode(notification),
        ),
    )


__all__ = ["send_notification_message"]
