from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_format_keyboard,
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_share_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT, DUEL_TYPE_OPEN
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeLimitExceededError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
)
from app.game.sessions.types import FriendChallengeSnapshot


def _friend_finished_for_user(*, challenge: FriendChallengeSnapshot, user_id: int) -> bool:
    if challenge.creator_user_id == user_id:
        return challenge.creator_finished_at is not None
    return challenge.opponent_finished_at is not None


async def handle_friend_challenge_type_selected(
    callback: CallbackQuery,
    *,
    friend_create_type_re,
) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    matched = friend_create_type_re.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    selected_type = matched.group(1)
    if selected_type == "tournament":
        await callback.message.answer(TEXTS_DE["msg.friend.challenge.tournament.soon"])
        await callback.answer()
        return
    await callback.message.answer(
        TEXTS_DE["msg.friend.challenge.create.format"],
        reply_markup=build_friend_challenge_format_keyboard(challenge_type=selected_type),
    )
    await callback.answer()


async def handle_friend_challenge_create_selected(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
    parse_friend_create_format,
    build_friend_invite_link,
    build_friend_plan_text,
    build_friend_ttl_text,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    parsed = parse_friend_create_format(callback.data)
    if parsed is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    selected_type, selected_rounds = parsed
    challenge_type = DUEL_TYPE_OPEN if selected_type == "open" else DUEL_TYPE_DIRECT
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        onboarding = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            challenge = await game_session_service.create_friend_challenge(
                session,
                creator_user_id=onboarding.user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc,
                challenge_type=challenge_type,
                total_rounds=selected_rounds,
            )
        except (FriendChallengePaymentRequiredError, FriendChallengeLimitExceededError):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(),
            )
            await callback.answer()
            return
    invite_link = await build_friend_invite_link(callback, challenge_id=str(challenge.challenge_id))
    if invite_link is None:
        await callback.message.answer(
            TEXTS_DE["msg.friend.challenge.created.fallback"].format(invite_token=challenge.invite_token),
            reply_markup=build_friend_challenge_back_keyboard(),
        )
        await callback.answer()
        return
    body_lines = [
        TEXTS_DE["msg.friend.challenge.created"],
        build_friend_plan_text(total_rounds=challenge.total_rounds),
        TEXTS_DE["msg.friend.challenge.created.short"],
    ]
    ttl_text = build_friend_ttl_text(challenge=challenge, now_utc=now_utc)
    if ttl_text is not None:
        body_lines.append(ttl_text)
    await callback.message.answer(
        "\n".join(body_lines),
        reply_markup=build_friend_challenge_share_keyboard(
            invite_link=invite_link,
            challenge_id=str(challenge.challenge_id),
            total_rounds=challenge.total_rounds,
        ),
    )
    await callback.answer()


async def handle_friend_copy_link(
    callback: CallbackQuery,
    *,
    friend_copy_link_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    build_friend_invite_link,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    challenge_id = parse_uuid_callback(pattern=friend_copy_link_re, callback_data=callback.data)
    if challenge_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            await game_session_service.get_friend_challenge_snapshot_for_user(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
        except (FriendChallengeNotFoundError, FriendChallengeAccessError):
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"])
            await callback.answer()
            return
    invite_link = await build_friend_invite_link(callback, challenge_id=str(challenge_id))
    if invite_link is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(invite_link)
    await callback.answer(TEXTS_DE["msg.friend.challenge.link.copied"])


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
    await callback.message.answer("\n".join(lines), reply_markup=build_friend_challenge_back_keyboard())
    await callback.answer()
