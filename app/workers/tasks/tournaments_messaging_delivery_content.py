from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED
from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext


def build_round_message_payload(
    *,
    context: TournamentRoundMessagingContext,
    user_id: int,
    resolve_match_context_fn: Callable[..., tuple[str | None, int | None]],
    build_standings_lines_fn: Callable[..., list[str]],
    build_completed_text_fn: Callable[..., str],
    build_round_text_fn: Callable[..., str],
    format_deadline_fn: Callable[..., str],
    build_keyboard_fn: Callable[..., object],
    add_share_button_fn: Callable[..., object],
    build_share_url_fn: Callable[..., str],
) -> tuple[str, Any]:
    play_challenge_id, opponent_user_id = resolve_match_context_fn(
        round_matches=context.round_matches,
        viewer_user_id=user_id,
    )
    standings_lines = build_standings_lines_fn(
        standings_user_ids=context.standings_user_ids,
        labels=context.labels,
        points_by_user=context.points_by_user,
        viewer_user_id=user_id,
    )
    if context.tournament.status == TOURNAMENT_STATUS_COMPLETED:
        text = build_completed_text_fn(
            tournament_name=context.tournament.name,
            tournament_format=context.tournament.format,
            place=context.place_by_user[user_id],
            my_points=context.points_by_user.get(user_id, "0"),
            standings_lines=standings_lines,
        )
    else:
        text = build_round_text_fn(
            tournament_name=context.tournament.name,
            tournament_format=context.tournament.format,
            round_no=max(1, int(context.tournament.current_round)),
            deadline_text=format_deadline_fn(context.tournament.round_deadline),
            opponent_label=(
                context.labels.get(opponent_user_id) if opponent_user_id is not None else None
            ),
            standings_lines=standings_lines,
        )
    keyboard = build_keyboard_fn(
        invite_code=context.tournament.invite_code,
        tournament_id=str(context.tournament.id),
        can_join=False,
        can_start=False,
        play_challenge_id=play_challenge_id,
        show_share_result=context.tournament.status == TOURNAMENT_STATUS_COMPLETED,
    )
    keyboard = add_share_button_fn(
        keyboard=keyboard,
        share_url=build_share_url_fn(
            invite_code=context.tournament.invite_code,
            tournament_name=context.tournament.name,
        ),
    )
    return text, keyboard
