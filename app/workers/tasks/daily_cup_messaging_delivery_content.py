from __future__ import annotations

from typing import Any

from app.workers.tasks.daily_cup_messaging_delivery_types import (
    DailyCupDeliveryContext,
    DailyCupDeliveryDependencies,
)


def _build_daily_cup_text(
    *,
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    user_id: int,
    rounds_total: int,
    opponent_label: str | None,
    standings_lines: list[str],
) -> str:
    if context.tournament.status == "COMPLETED":
        return dependencies.build_completed_text(
            place=context.place_by_user[user_id],
            my_points=context.points_by_user.get(user_id, "0"),
            standings_lines=standings_lines,
        )
    return dependencies.build_round_text(
        round_no=max(1, int(context.tournament.current_round)),
        rounds_total=rounds_total,
        deadline_text=dependencies.format_deadline(context.tournament.round_deadline),
        opponent_label=opponent_label,
        standings_lines=standings_lines,
    )


def _build_share_url(
    *,
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    user_id: int,
) -> str | None:
    if context.tournament.status != "COMPLETED":
        return None
    return dependencies.build_daily_cup_share_url(
        base_link=dependencies.public_bot_link(),
        share_text=dependencies.share_template.format(
            place=context.place_by_user[user_id],
            total=context.participants_total,
            points=context.points_by_user.get(user_id, "0"),
        ),
    )


def build_daily_cup_message_payload(
    *,
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    rounds_total: int,
    user_id: int,
) -> tuple[str, Any]:
    play_challenge_id, opponent_user_id = dependencies.resolve_match_context(
        round_matches=context.round_matches,
        viewer_user_id=user_id,
    )
    opponent_label = context.labels.get(opponent_user_id) if opponent_user_id is not None else None
    standings_lines = dependencies.build_standings_lines(
        standings_user_ids=context.standings_user_ids,
        labels=context.labels,
        points_by_user=context.points_by_user,
        viewer_user_id=user_id,
        tie_breaks_by_user=(
            context.tie_breaks_by_user if context.tournament.status == "COMPLETED" else None
        ),
    )
    text = _build_daily_cup_text(
        context=context,
        dependencies=dependencies,
        user_id=user_id,
        rounds_total=rounds_total,
        opponent_label=opponent_label,
        standings_lines=standings_lines,
    )
    keyboard = dependencies.build_daily_cup_lobby_keyboard(
        tournament_id=str(context.tournament.id),
        can_join=False,
        play_challenge_id=play_challenge_id,
        play_button_text="Runde starten",
        show_share_result=context.tournament.status == "COMPLETED",
        show_proof_card=context.tournament.status == "COMPLETED",
        share_url=_build_share_url(context=context, dependencies=dependencies, user_id=user_id),
    )
    return text, keyboard


__all__ = ["build_daily_cup_message_payload"]
