from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardMarkup

from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_TYPE
from app.game.arena_duels.types import ArenaBeatenNotification
from app.workers.tasks.arena_duels_notification_content import (
    build_arena_beaten_notification_keyboard,
    build_notification_text,
    classify_beaten_notification_action_mode,
)


def _notification(
    *,
    previous_score: int = 6,
    previous_time_ms: int = 48_000,
    new_score: int = 7,
    new_time_ms: int = 52_000,
) -> ArenaBeatenNotification:
    return ArenaBeatenNotification(
        arena_duel_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        previous_best_attempt_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        previous_best_user_id=11,
        previous_best_score=previous_score,
        previous_best_time_ms=previous_time_ms,
        new_best_attempt_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        new_best_user_id=22,
        new_best_score=new_score,
        new_best_time_ms=new_time_ms,
        notification_type=ARENA_BEATEN_NOTIFICATION_TYPE,
    )


def _callbacks(reply_markup: InlineKeyboardMarkup) -> list[str]:
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def test_beaten_notification_same_score_time_loss_uses_premium_revanche_moment() -> None:
    notification = _notification(
        previous_score=6,
        previous_time_ms=48_000,
        new_score=6,
        new_time_ms=41_000,
    )

    text = build_notification_text(notification=notification, challenger_label="@anna")
    keyboard = build_arena_beaten_notification_keyboard(
        source_attempt_id=str(notification.new_best_attempt_id),
        action_mode=classify_beaten_notification_action_mode(notification),
    )

    assert "nur wegen der Zeit" in text
    assert "7 Sekunden schneller." in text
    assert "Revanche?" in text
    assert _callbacks(keyboard) == [
        "arena:revanche:cccccccc-cccc-cccc-cccc-cccccccccccc",
        "buy:FRIEND_CHALLENGE_5:duel:beaten_result",
        "buy:PREMIUM_WEEK:duel:beaten_result",
        "arena:list",
    ]


def test_beaten_notification_large_score_gap_hides_monetization_rows() -> None:
    notification = _notification(
        previous_score=4,
        previous_time_ms=48_000,
        new_score=6,
        new_time_ms=52_000,
    )

    text = build_notification_text(notification=notification, challenger_label="@anna")
    keyboard = build_arena_beaten_notification_keyboard(
        source_attempt_id=str(notification.new_best_attempt_id),
        action_mode=classify_beaten_notification_action_mode(notification),
    )

    assert "2 richtige Antworten Unterschied." in text
    assert "Starte eine Revanche" in text
    assert _callbacks(keyboard) == [
        "arena:revanche:cccccccc-cccc-cccc-cccc-cccccccccccc",
        "arena:list",
    ]


def test_beaten_notification_weak_result_only_links_back_to_arena() -> None:
    notification = _notification(
        previous_score=2,
        previous_time_ms=48_000,
        new_score=7,
        new_time_ms=52_000,
    )

    text = build_notification_text(notification=notification, challenger_label="@anna")
    keyboard = build_arena_beaten_notification_keyboard(
        source_attempt_id=str(notification.new_best_attempt_id),
        action_mode=classify_beaten_notification_action_mode(notification),
    )

    assert "Wähle ein neues Duell in der Arena." in text
    assert _callbacks(keyboard) == ["arena:list"]
