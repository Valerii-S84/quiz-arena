from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.game.tournaments.constants import daily_cup_max_rounds_for_participants
from app.services.telegram_delivery import (
    TelegramDeliveryTarget,
    build_delivery_idempotency_key,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)
from app.workers.tasks.daily_cup_messaging_text import (
    build_completed_text,
    build_round_text,
    build_standings_lines,
)
from app.workers.tasks.tournaments_messaging_text import (
    format_deadline,
    is_message_not_modified_error,
    resolve_match_context,
)


async def deliver_daily_cup_messages(
    *,
    bot: Any,
    tournament: Tournament,
    round_matches: list[TournamentMatch],
    standings_user_ids: list[int],
    labels: dict[int, str],
    telegram_targets: dict[int, int],
    points_by_user: dict[int, str],
    tie_breaks_by_user: dict[int, str],
    place_by_user: dict[int, int],
    participant_rows: dict[int, TournamentParticipant],
    participants_total: int,
) -> dict[str, Any]:
    sent = edited = failed = skipped = 0
    new_message_ids: dict[int, int] = {}
    replaced_message_ids: dict[int, int] = {}
    rounds_total = daily_cup_max_rounds_for_participants(participants_total=participants_total)
    happened_at = datetime.now(timezone.utc)
    flow = "daily_cup_round_messaging"
    task_name = "daily_cup.run_daily_cup_round_messaging"
    correlation_id = str(tournament.id)

    for user_id in standings_user_ids:
        chat_id = telegram_targets.get(user_id)
        existing_message_id = participant_rows[user_id].standings_message_id
        target = _daily_cup_round_delivery_target(
            flow=flow,
            task_name=task_name,
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            delivery_operation=_delivery_operation(existing_message_id),
        )
        delivery = await prepare_telegram_delivery(target=target, happened_at=happened_at)
        if not delivery.should_send:
            skipped += 1
            continue

        play_challenge_id, opponent_user_id = resolve_match_context(
            round_matches=round_matches,
            viewer_user_id=user_id,
        )
        standings_lines = build_standings_lines(
            standings_user_ids=standings_user_ids,
            labels=labels,
            points_by_user=points_by_user,
            viewer_user_id=user_id,
            tie_breaks_by_user=tie_breaks_by_user if tournament.status == "COMPLETED" else None,
        )
        if tournament.status == "COMPLETED":
            text = build_completed_text(
                place=place_by_user[user_id],
                my_points=points_by_user.get(user_id, "0"),
                standings_lines=standings_lines,
            )
        else:
            text = build_round_text(
                round_no=max(1, int(tournament.current_round)),
                rounds_total=rounds_total,
                deadline_text=format_deadline(tournament.round_deadline),
                opponent_label=(
                    labels.get(opponent_user_id) if opponent_user_id is not None else None
                ),
                standings_lines=standings_lines,
            )
        keyboard = build_daily_cup_lobby_keyboard(
            tournament_id=str(tournament.id),
            can_join=False,
            play_challenge_id=play_challenge_id,
            play_button_text="Runde starten",
            show_share_result=tournament.status == "COMPLETED",
            show_proof_card=tournament.status == "COMPLETED",
            share_url=(
                build_daily_cup_share_url(
                    base_link=public_bot_link(),
                    share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
                        place=place_by_user[user_id],
                        total=participants_total,
                        points=points_by_user.get(user_id, "0"),
                    ),
                )
                if tournament.status == "COMPLETED"
                else None
            ),
        )
        if existing_message_id is None:
            try:
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            except Exception as exc:
                failed += 1
                await mark_telegram_delivery_failed(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                    exc=exc,
                )
                continue
            await mark_telegram_delivery_sent(
                idempotency_key=target.idempotency_key,
                happened_at=happened_at,
            )
            sent += 1
            new_message_ids[user_id] = int(message.message_id)
            continue
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(existing_message_id),
                text=text,
                reply_markup=keyboard,
            )
            await mark_telegram_delivery_sent(
                idempotency_key=target.idempotency_key,
                happened_at=happened_at,
            )
            edited += 1
        except Exception as exc:
            if is_message_not_modified_error(exc):
                await mark_telegram_delivery_sent(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                )
                edited += 1
                continue
            try:
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            except Exception as send_exc:
                failed += 1
                await mark_telegram_delivery_failed(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                    exc=send_exc,
                )
                continue
            await mark_telegram_delivery_sent(
                idempotency_key=target.idempotency_key,
                happened_at=happened_at,
            )
            sent += 1
            replaced_message_ids[user_id] = int(message.message_id)

    return {
        "sent": sent,
        "edited": edited,
        "failed": failed,
        "skipped": skipped,
        "new_message_ids": new_message_ids,
        "replaced_message_ids": replaced_message_ids,
    }


def _daily_cup_round_delivery_target(
    *,
    flow: str,
    task_name: str,
    correlation_id: str,
    user_id: int,
    chat_id: int | None,
    delivery_operation: str,
) -> TelegramDeliveryTarget:
    target_id = f"{user_id}:{delivery_operation}"
    return TelegramDeliveryTarget(
        flow=flow,
        task_name=task_name,
        correlation_id=correlation_id,
        target_type="user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow=flow,
            correlation_id=correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        telegram_user_id=chat_id,
        chat_id=chat_id,
        safe_context={"tournament_id": correlation_id, "user_id": user_id},
    )


def _delivery_operation(existing_message_id: int | None) -> str:
    if existing_message_id is None:
        return "send"
    return f"edit:{int(existing_message_id)}"
