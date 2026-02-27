from __future__ import annotations

from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.friend_challenge import build_friend_challenge_share_url
from app.bot.texts.de import TEXTS_DE
from app.game.friend_challenges.constants import DUEL_TYPE_OPEN
from app.game.sessions.types import FriendChallengeSnapshot


def _friend_finished_for_user(*, challenge: FriendChallengeSnapshot, user_id: int) -> bool:
    if challenge.creator_user_id == user_id:
        return challenge.creator_finished_at is not None
    return challenge.opponent_finished_at is not None


def _build_repost_share_text(*, total_rounds: int) -> str:
    rounds = max(1, int(total_rounds))
    return f"⚔️ Ich fordere dich heraus! Kannst du mich schlagen? ({rounds} Fragen)"


async def _build_open_repost_share_url(
    callback: CallbackQuery,
    *,
    challenge_id: str,
    total_rounds: int,
) -> str | None:
    bot = callback.bot
    if bot is None:
        return None
    try:
        me = await bot.get_me()
    except Exception:
        return None
    if not me.username:
        return None
    invite_link = f"https://t.me/{me.username}?start=duel_{challenge_id}"
    return build_friend_challenge_share_url(
        base_link=invite_link,
        share_text=_build_repost_share_text(total_rounds=total_rounds),
    )


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
    open_lines: list[str] = []
    completed_lines: list[str] = []
    my_turn_challenges: list[FriendChallengeSnapshot] = []
    open_challenges: list[FriendChallengeSnapshot] = []
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
            open_lines.append(f"• Offene Herausforderung — {challenge.total_rounds} Fragen")
            open_challenges.append(challenge)
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
    if open_lines:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.open"], *open_lines])
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
    for challenge in open_challenges:
        share_url = await _build_open_repost_share_url(
            callback,
            challenge_id=str(challenge.challenge_id),
            total_rounds=challenge.total_rounds,
        )
        if share_url:
            action_rows.append([InlineKeyboardButton(text="📤 Repost", url=share_url)])
        else:
            action_rows.append(
                [
                    InlineKeyboardButton(
                        text="📤 Repost",
                        callback_data=f"friend:copy:{challenge.challenge_id}",
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
