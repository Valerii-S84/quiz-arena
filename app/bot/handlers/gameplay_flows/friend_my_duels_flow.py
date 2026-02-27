from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import build_friend_challenge_back_keyboard
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

    my_turn: list[str] = []
    waiting: list[str] = []
    open_items: list[str] = []
    completed: list[str] = []
    for challenge in duels:
        opponent_label = await resolve_opponent_label(
            challenge=challenge,
            user_id=snapshot.user_id,
        )
        duel_line = f"• vs {opponent_label} — {challenge.total_rounds} Fragen"
        if challenge.status in {"COMPLETED", "EXPIRED", "WALKOVER", "CANCELED"}:
            completed.append(duel_line)
            continue
        if challenge.challenge_type == DUEL_TYPE_OPEN and challenge.opponent_user_id is None:
            open_items.append(f"• Offene Herausforderung — {challenge.total_rounds} Fragen")
            continue
        if _friend_finished_for_user(challenge=challenge, user_id=snapshot.user_id):
            waiting.append(f"{duel_line} — Wartet")
        else:
            my_turn.append(f"{duel_line} — Dein Zug!")

    lines = [TEXTS_DE["msg.friend.challenge.my.title"]]
    if my_turn:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.my_turn"], *my_turn])
    if waiting:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.waiting"], *waiting])
    if open_items:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.open"], *open_items])
    if completed:
        lines.extend(["", TEXTS_DE["msg.friend.challenge.my.completed"], *completed[:10]])
    if len(lines) == 1:
        lines.append(TEXTS_DE["msg.friend.challenge.my.empty"])

    await callback.message.answer(
        "\n".join(lines),
        reply_markup=build_friend_challenge_back_keyboard(),
    )
    await callback.answer()
