from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.texts.de import TEXTS_DE
from app.game.friend_challenges.constants import DUEL_TYPE_OPEN
from app.game.sessions.types import FriendChallengeSnapshot


def _friend_finished_for_user(*, challenge: FriendChallengeSnapshot, user_id: int) -> bool:
    if challenge.creator_user_id == user_id:
        return challenge.creator_finished_at is not None
    return challenge.opponent_finished_at is not None


async def handle_friend_my_duels(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    from datetime import datetime, timezone

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        duels = await game_session_service.list_friend_challenges_for_user(
            session,
            user_id=snapshot.user_id,
            now_utc=now_utc,
            limit=20,
        )

    my_turn_lines: list[str] = []
    waiting_lines: list[str] = []
    completed_lines: list[str] = []
    my_turn_challenges: list[FriendChallengeSnapshot] = []
    completed_challenges: list[FriendChallengeSnapshot] = []
    for challenge in duels:
        opponent_label = await resolve_opponent_label(
            challenge=challenge,
            user_id=snapshot.user_id,
        )
        duel_line = f"• vs {opponent_label} — {challenge.total_rounds} Fragen"
        if challenge.status in {"COMPLETED", "EXPIRED", "WALKOVER", "CANCELED"}:
            completed_lines.append(duel_line)
            completed_challenges.append(challenge)
            continue
        if challenge.challenge_type == DUEL_TYPE_OPEN and challenge.opponent_user_id is None:
            # HIDDEN: open challenge disabled for now.
            continue
        if _friend_finished_for_user(challenge=challenge, user_id=snapshot.user_id):
            waiting_lines.append(f"{duel_line} — Wartet")
        else:
            my_turn_lines.append(f"{duel_line} — Dein Zug!")
            my_turn_challenges.append(challenge)

    lines = [TEXTS_DE["msg.friend.challenge.my.title"]]
    if my_turn_lines:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.my_turn"], *my_turn_lines])
    if waiting_lines:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.waiting"], *waiting_lines])
    if completed_lines:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.completed"], *completed_lines[:10]])
    if len(lines) == 1:
        lines.append(TEXTS_DE["msg.friend.challenge.my.empty"])

    action_rows: list[list[InlineKeyboardButton]] = []
    for challenge in my_turn_challenges:
        action_rows.append(
            [
                InlineKeyboardButton(
                    text="▶️ Spielen",
                    callback_data=f"friend:next:{challenge.challenge_id}",
                )
            ]
        )
    for challenge in completed_challenges[:10]:
        action_rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Revanche",
                    callback_data=f"friend:rematch:{challenge.challenge_id}",
                )
            ]
        )
    action_rows.append([InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")])

    await callback.message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=action_rows),
    )
    await callback.answer()
