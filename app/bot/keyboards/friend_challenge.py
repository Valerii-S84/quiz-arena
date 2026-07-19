from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import friend_challenge_share
from app.bot.keyboards.duels_access import build_duel_monetization_rows
from app.game.arena_duels.analytics import ArenaPaywallContext
from app.game.duels import rollout as duel_rollout
from app.game.duels.constants import (
    ARENA_LIST_CALLBACK,
    ARENA_PUBLISH_FRIEND_CALLBACK_PREFIX,
    DUEL_QUESTION_COUNT,
    FRIEND_DUEL_CREATE_CALLBACK,
)
from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE, DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

build_friend_challenge_share_url = friend_challenge_share.build_friend_challenge_share_url
build_friend_challenge_share_keyboard = friend_challenge_share.build_friend_challenge_share_keyboard
build_friend_challenge_share_confirmed_keyboard = (
    friend_challenge_share.build_friend_challenge_share_confirmed_keyboard
)
build_friend_challenge_result_share_keyboard = (
    friend_challenge_share.build_friend_challenge_result_share_keyboard
)


def build_friend_challenge_next_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ NAECHSTE RUNDE", callback_data=f"friend:next:{challenge_id}"
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_challenge_start_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Jetzt spielen",
                    callback_data=f"friend:next:{challenge_id}",
                )
            ],
        ]
    )


def _can_publish_friend_challenge_to_arena(
    *,
    challenge: FriendChallengeSnapshot | None,
    user_id: int | None,
) -> bool:
    if challenge is None or user_id is None:
        return False
    return (
        duel_rollout.is_canonical_duels_enabled()
        and challenge.creator_user_id == user_id
        and challenge.opponent_user_id is None
        and challenge.challenge_type == DUEL_TYPE_DIRECT
        and challenge.status == DUEL_STATUS_CREATOR_DONE
        and int(challenge.total_rounds) == DUEL_QUESTION_COUNT
        and challenge.creator_finished_at is not None
        and challenge.tournament_match_id is None
    )


def build_friend_challenge_back_keyboard(
    *,
    challenge: FriendChallengeSnapshot | None = None,
    user_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if _can_publish_friend_challenge_to_arena(challenge=challenge, user_id=user_id):
        assert challenge is not None
        rows.append(
            [
                InlineKeyboardButton(
                    text="🏟 In der Arena veröffentlichen",
                    callback_data=f"{ARENA_PUBLISH_FRIEND_CALLBACK_PREFIX}{challenge.challenge_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_finished_keyboard(
    *,
    challenge_id: str,
    share_url: str | None = None,
    include_share: bool = True,
    show_best_of_three: bool = True,
    show_next_series_game: bool = False,
) -> InlineKeyboardMarkup:
    del share_url, show_best_of_three, show_next_series_game
    rows: list[list[InlineKeyboardButton]] = []
    if duel_rollout.is_canonical_duels_enabled():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Revanche",
                    callback_data=f"friend:rematch:{challenge_id}",
                )
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="🏟 Offene Arena", callback_data=ARENA_LIST_CALLBACK)]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if include_share:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📤 Ergebnis teilen",
                    callback_data=f"friend:share:result:{challenge_id}",
                )
            ]
        )
    if duel_rollout.is_canonical_duels_enabled():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Revanche",
                    callback_data=f"friend:rematch:{challenge_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_limit_keyboard(
    *,
    paywall_context: ArenaPaywallContext = "friend_create_limit",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *build_duel_monetization_rows(paywall_context=paywall_context),
            [InlineKeyboardButton(text="↩️ Später", callback_data="home:open")],
        ]
    )


def build_friend_open_taken_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Freundesduell erstellen",
                    callback_data=FRIEND_DUEL_CREATE_CALLBACK,
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_pending_expired_keyboard(
    *,
    challenge_id: str,
    can_publish_to_arena: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_publish_to_arena and duel_rollout.is_canonical_duels_enabled():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🏟 In der Arena veröffentlichen",
                    callback_data=f"{ARENA_PUBLISH_FRIEND_CALLBACK_PREFIX}{challenge_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⏳ Weiter warten", callback_data="home:open")])
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Schließen",
                callback_data=f"friend:delete:{challenge_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
