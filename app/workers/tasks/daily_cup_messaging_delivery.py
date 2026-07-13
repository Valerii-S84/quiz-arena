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
    begin_telegram_delivery_dispatch,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)
from app.workers.tasks import messaging_fallback_delivery as fallback_delivery
from app.workers.tasks.daily_cup_message_delivery_persistence import persist_daily_cup_sent_message
from app.workers.tasks.daily_cup_messaging_delivery_runtime import (
    deliver_daily_cup_messages_with_dependencies,
)
from app.workers.tasks.daily_cup_messaging_delivery_targets import (
    daily_cup_content_version,
    daily_cup_delivery_result,
    daily_cup_round_delivery_target,
    delivery_operation,
    fallback_delivery_operation,
)
from app.workers.tasks.daily_cup_messaging_delivery_types import (
    DailyCupDeliveryContext,
    DailyCupDeliveryDependencies,
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
    dependencies = DailyCupDeliveryDependencies(
        build_daily_cup_lobby_keyboard=build_daily_cup_lobby_keyboard,
        build_daily_cup_share_url=build_daily_cup_share_url,
        public_bot_link=public_bot_link,
        daily_cup_max_rounds_for_participants=daily_cup_max_rounds_for_participants,
        daily_cup_content_version=daily_cup_content_version,
        daily_cup_round_delivery_target=daily_cup_round_delivery_target,
        delivery_operation=delivery_operation,
        fallback_delivery_operation=fallback_delivery_operation,
        daily_cup_delivery_result=daily_cup_delivery_result,
        build_completed_text=build_completed_text,
        build_round_text=build_round_text,
        build_standings_lines=build_standings_lines,
        format_deadline=format_deadline,
        is_message_not_modified_error=is_message_not_modified_error,
        resolve_match_context=resolve_match_context,
        prepare_telegram_delivery=prepare_telegram_delivery,
        begin_telegram_delivery_dispatch=begin_telegram_delivery_dispatch,
        mark_telegram_delivery_failed=mark_telegram_delivery_failed,
        mark_telegram_delivery_sent=mark_telegram_delivery_sent,
        persist_daily_cup_sent_message=persist_daily_cup_sent_message,
        fallback_delivery=fallback_delivery,
        share_template=TEXTS_DE["msg.daily_cup.share_template"],
        happened_at=lambda: datetime.now(timezone.utc),
    )
    context = DailyCupDeliveryContext(
        bot=bot,
        tournament=tournament,
        round_matches=round_matches,
        standings_user_ids=standings_user_ids,
        labels=labels,
        telegram_targets=telegram_targets,
        points_by_user=points_by_user,
        tie_breaks_by_user=tie_breaks_by_user,
        place_by_user=place_by_user,
        participant_rows=participant_rows,
        participants_total=participants_total,
    )
    return await deliver_daily_cup_messages_with_dependencies(
        context=context,
        dependencies=dependencies,
    )
