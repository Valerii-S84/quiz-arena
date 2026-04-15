from __future__ import annotations
from collections.abc import Collection, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED, TOURNAMENT_TYPE_PRIVATE
@dataclass(frozen=True, slots=True)
class TournamentRoundMessagingContext:
    parsed_tournament_id: UUID
    tournament: Any
    standings_user_ids: list[int]
    points_by_user: dict[int, str]
    place_by_user: dict[int, int]
    participant_rows: dict[int, Any]
    telegram_targets: dict[int, int]
    labels: dict[int, str]
    round_matches: list[Any]
@dataclass(frozen=True, slots=True)
class TournamentRoundDeliveryResult:
    sent: int
    edited: int
    failed: int
    new_message_ids: dict[int, int]
    replaced_message_ids: dict[int, int]
async def load_round_messaging_context(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    tournaments_repo: Any,
    participants_repo: Any,
    users_repo: Any,
    matches_repo: Any,
    format_points_fn: Callable[..., str],
    round_statuses: Collection[str],
    format_user_label_fn: Callable[..., str],
) -> TournamentRoundMessagingContext | None:
    tournament = await tournaments_repo.get_by_id(session, parsed_tournament_id)
    if (
        tournament is None
        or tournament.type != TOURNAMENT_TYPE_PRIVATE
        or tournament.status in {"REGISTRATION", "CANCELED"}
    ):
        return None
    participants = await participants_repo.list_for_tournament(
        session,
        tournament_id=parsed_tournament_id,
    )
    if not participants:
        return None
    users = await users_repo.list_by_ids(session, [int(item.user_id) for item in participants])
    labels = {
        int(user.id): format_user_label_fn(username=user.username, first_name=user.first_name)
        for user in users
    }
    telegram_targets = {int(user.id): int(user.telegram_user_id) for user in users}
    round_matches: list[Any] = []
    if tournament.status in round_statuses:
        round_matches = await matches_repo.list_by_tournament_round(
            session,
            tournament_id=parsed_tournament_id,
            round_no=int(tournament.current_round),
        )

    standings_user_ids = [int(item.user_id) for item in participants]
    points_by_user = {int(item.user_id): item.score for item in participants}
    return TournamentRoundMessagingContext(
        parsed_tournament_id=parsed_tournament_id,
        tournament=tournament,
        standings_user_ids=standings_user_ids,
        points_by_user={user_id: format_points_fn(score) for user_id, score in points_by_user.items()},
        place_by_user={user_id: place for place, user_id in enumerate(standings_user_ids, start=1)},
        participant_rows={int(item.user_id): item for item in participants},
        telegram_targets=telegram_targets,
        labels=labels,
        round_matches=round_matches,
    )
async def deliver_round_messages(
    *,
    context: TournamentRoundMessagingContext,
    build_bot_fn: Callable[[], Any],
    resolve_match_context_fn: Callable[..., tuple[str | None, int | None]],
    build_standings_lines_fn: Callable[..., list[str]],
    build_completed_text_fn: Callable[..., str],
    build_round_text_fn: Callable[..., str],
    format_deadline_fn: Callable[..., str],
    build_keyboard_fn: Callable[..., object],
    add_share_button_fn: Callable[..., object],
    build_share_url_fn: Callable[..., str],
    is_message_not_modified_error_fn: Callable[[Exception], bool],
    logger: Any,
) -> TournamentRoundDeliveryResult:
    sent = 0
    edited = 0
    failed = 0
    new_message_ids: dict[int, int] = {}
    replaced_message_ids: dict[int, int] = {}
    bot = build_bot_fn()
    try:
        for user_id in context.standings_user_ids:
            chat_id = context.telegram_targets.get(user_id)
            if chat_id is None:
                failed += 1
                continue

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
            existing_message_id = context.participant_rows[user_id].standings_message_id
            if existing_message_id is None:
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
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
                edited += 1
            except Exception as exc:
                if is_message_not_modified_error_fn(exc):
                    edited += 1
                    continue
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
                sent += 1
                replaced_message_ids[user_id] = int(message.message_id)
    except Exception as exc:
        logger.warning(
            "private_tournament_round_message_failed",
            tournament_id=str(context.parsed_tournament_id),
            error_type=type(exc).__name__,
        )
        failed += 1
    finally:
        await bot.session.close()

    return TournamentRoundDeliveryResult(
        sent=sent,
        edited=edited,
        failed=failed,
        new_message_ids=new_message_ids,
        replaced_message_ids=replaced_message_ids,
    )
async def persist_standings_message_ids(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    participants_repo: Any,
    new_message_ids: dict[int, int],
    replaced_message_ids: dict[int, int],
) -> None:
    for user_id, message_id in new_message_ids.items():
        await participants_repo.set_standings_message_id_if_missing(
            session,
            tournament_id=parsed_tournament_id,
            user_id=user_id,
            message_id=message_id,
        )
    for user_id, message_id in replaced_message_ids.items():
        await participants_repo.set_standings_message_id(
            session,
            tournament_id=parsed_tournament_id,
            user_id=user_id,
            message_id=message_id,
        )
__all__ = ["TournamentRoundDeliveryResult", "TournamentRoundMessagingContext", "deliver_round_messages", "load_round_messaging_context", "persist_standings_message_ids"]
