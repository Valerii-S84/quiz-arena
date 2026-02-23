from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from aiogram.types import CallbackQuery

if TYPE_CHECKING:
    from app.game.sessions.types import FriendChallengeSnapshot


class _SessionFactory(Protocol):
    def begin(self): ...


class _UsersRepo(Protocol):
    @staticmethod
    async def get_by_id(session, user_id: int): ...


def _friend_opponent_user_id(*, challenge: FriendChallengeSnapshot, user_id: int) -> int | None:
    if challenge.creator_user_id == user_id:
        return challenge.opponent_user_id
    if challenge.opponent_user_id == user_id:
        return challenge.creator_user_id
    return None


async def _resolve_opponent_label(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    session_local: _SessionFactory,
    users_repo: _UsersRepo,
    format_user_label,
) -> str:
    opponent_user_id = _friend_opponent_user_id(challenge=challenge, user_id=user_id)
    if opponent_user_id is None:
        return "Freund"

    async with session_local.begin() as session:
        opponent = await users_repo.get_by_id(session, opponent_user_id)

    if opponent is None:
        return "Freund"
    return format_user_label(
        username=opponent.username,
        first_name=opponent.first_name,
        fallback="Freund",
    )


async def _notify_opponent(
    callback: CallbackQuery,
    *,
    opponent_user_id: int | None,
    text: str,
    session_local: _SessionFactory,
    users_repo: _UsersRepo,
    reply_markup=None,
) -> None:
    if opponent_user_id is None or callback.from_user is None:
        return

    async with session_local.begin() as session:
        opponent = await users_repo.get_by_id(session, opponent_user_id)
    if opponent is None:
        return

    try:
        await callback.bot.send_message(
            chat_id=opponent.telegram_user_id,
            text=text,
            reply_markup=reply_markup,
        )
    except Exception:
        return


async def _build_friend_invite_link(callback: CallbackQuery, *, invite_token: str) -> str | None:
    try:
        me = await callback.bot.get_me()
    except Exception:
        return None
    if not me.username:
        return None
    return f"https://t.me/{me.username}?start=fc_{invite_token}"


async def _build_friend_result_share_url(
    callback: CallbackQuery,
    *,
    proof_card_text: str,
    share_cta_text: str,
    build_share_url,
) -> str | None:
    try:
        me = await callback.bot.get_me()
    except Exception:
        return None
    if not me.username:
        return None

    share_text = "\n".join([proof_card_text, "", share_cta_text])
    return build_share_url(
        base_link=f"https://t.me/{me.username}",
        share_text=share_text,
    )
