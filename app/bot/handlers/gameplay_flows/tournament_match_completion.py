from __future__ import annotations

from typing import Protocol

from aiogram.types import CallbackQuery


class _Answerable(Protocol):
    async def answer(self, *args, **kwargs) -> object: ...


async def handle_completed_tournament_match(
    callback: CallbackQuery,
    *,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    opponent_user_id: int | None,
    idempotent_replay: bool,
    answerable: _Answerable,
    session_local,
    resolve_opponent_label,
    notify_opponent,
    resolve_tournament_id_for_match,
    resolve_tournament_view_callback_data_for_match,
    resolve_tournament_place_for_user,
    build_tournament_post_match_keyboard,
    build_tournament_post_match_text,
    enqueue_tournament_post_match_updates,
) -> bool:
    if challenge.tournament_match_id is None:
        return False

    tournament_id = await resolve_tournament_id_for_match(
        session_local=session_local,
        tournament_match_id=challenge.tournament_match_id,
    )
    tournament_view_callback_data = await resolve_tournament_view_callback_data_for_match(
        session_local=session_local,
        tournament_match_id=challenge.tournament_match_id,
    )
    try:
        my_place, participants_total = await resolve_tournament_place_for_user(
            session_local=session_local,
            tournament_match_id=challenge.tournament_match_id,
            user_id=snapshot_user_id,
        )
    except AttributeError:
        my_place, participants_total = None, None

    tournament_keyboard = build_tournament_post_match_keyboard(
        tournament_id=tournament_id,
        tournament_view_callback_data=tournament_view_callback_data,
    )
    await answerable.answer(
        build_tournament_post_match_text(
            challenge=challenge,
            user_id=snapshot_user_id,
            opponent_label=opponent_label,
            place=my_place,
            participants_total=participants_total,
        ),
        reply_markup=tournament_keyboard,
    )
    if not idempotent_replay and opponent_user_id is not None:
        opponent_label_for_opponent = await resolve_opponent_label(
            challenge=challenge,
            user_id=opponent_user_id,
        )
        try:
            opponent_place, opponent_total = await resolve_tournament_place_for_user(
                session_local=session_local,
                tournament_match_id=challenge.tournament_match_id,
                user_id=opponent_user_id,
            )
        except AttributeError:
            opponent_place, opponent_total = None, None
        await notify_opponent(
            callback,
            opponent_user_id=opponent_user_id,
            text=build_tournament_post_match_text(
                challenge=challenge,
                user_id=opponent_user_id,
                opponent_label=opponent_label_for_opponent,
                place=opponent_place,
                participants_total=opponent_total,
            ),
            reply_markup=tournament_keyboard,
        )
    if not idempotent_replay and tournament_id is not None:
        enqueue_tournament_post_match_updates(tournament_id=tournament_id)
    return True
