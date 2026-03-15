from __future__ import annotations

from aiogram import F, Router

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_friend_challenge_lobby import (
    handle_create_tournament_start,
    handle_friend_challenge_copy_link,
    handle_friend_challenge_create,
    handle_friend_challenge_create_selected,
    handle_friend_challenge_invite_required,
    handle_friend_challenge_invite_sent,
    handle_friend_challenge_type_selected,
    handle_friend_my_duels,
)
from app.bot.handlers.gameplay_friend_challenge_manage import (
    handle_friend_delete,
    handle_friend_open_repost,
)
from app.bot.handlers.gameplay_friend_challenge_progress import (
    handle_friend_challenge_next,
    handle_friend_challenge_rematch,
    handle_friend_challenge_series_best3,
    handle_friend_challenge_series_next,
    handle_friend_challenge_share_result,
)


def register(router: Router) -> None:
    router.callback_query(F.data == "friend:challenge:create")(handle_friend_challenge_create)
    router.callback_query(F.data == "create_tournament_start")(handle_create_tournament_start)
    # HIDDEN: open challenge disabled for now.
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_CREATE_TYPE_RE))(
        handle_friend_challenge_type_selected
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_CREATE_FORMAT_RE))(
        handle_friend_challenge_create_selected
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_COPY_LINK_RE))(
        handle_friend_challenge_copy_link
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_OPEN_REPOST_RE))(
        handle_friend_open_repost
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_DELETE_RE))(handle_friend_delete)
    router.callback_query(F.data == "friend:my:duels")(handle_friend_my_duels)
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_REMATCH_RE))(
        handle_friend_challenge_rematch
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_SERIES_BEST3_RE))(
        handle_friend_challenge_series_best3
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_SERIES_NEXT_RE))(
        handle_friend_challenge_series_next
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_SHARE_RESULT_RE))(
        handle_friend_challenge_share_result
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_INVITE_SENT_RE))(
        handle_friend_challenge_invite_sent
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_INVITE_REQUIRED_RE))(
        handle_friend_challenge_invite_required
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_NEXT_RE))(
        handle_friend_challenge_next
    )
