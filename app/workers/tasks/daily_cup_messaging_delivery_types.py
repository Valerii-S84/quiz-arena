from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament


@dataclass(frozen=True, slots=True)
class DailyCupDeliveryContext:
    bot: Any
    tournament: Tournament
    round_matches: list[TournamentMatch]
    standings_user_ids: list[int]
    labels: dict[int, str]
    telegram_targets: dict[int, int]
    points_by_user: dict[int, str]
    tie_breaks_by_user: dict[int, str]
    place_by_user: dict[int, int]
    participant_rows: dict[int, TournamentParticipant]
    participants_total: int


@dataclass(frozen=True, slots=True)
class DailyCupDeliveryDependencies:
    build_daily_cup_lobby_keyboard: Any
    build_daily_cup_share_url: Any
    public_bot_link: Any
    daily_cup_max_rounds_for_participants: Any
    daily_cup_content_version: Any
    daily_cup_round_delivery_target: Any
    delivery_operation: Any
    fallback_delivery_operation: Any
    daily_cup_delivery_result: Any
    build_completed_text: Any
    build_round_text: Any
    build_standings_lines: Any
    format_deadline: Any
    is_message_not_modified_error: Any
    resolve_match_context: Any
    prepare_telegram_delivery: Any
    begin_telegram_delivery_dispatch: Any
    mark_telegram_delivery_failed: Any
    mark_telegram_delivery_sent: Any
    persist_daily_cup_sent_message: Any
    fallback_delivery: Any
    share_template: str
    happened_at: Any


@dataclass(slots=True)
class DailyCupDeliveryState:
    sent: int = 0
    edited: int = 0
    failed: int = 0
    skipped: int = 0
    new_message_ids: dict[int, int] = field(default_factory=dict)
    replaced_message_ids: dict[int, int] = field(default_factory=dict)

    def to_result(self, dependencies: DailyCupDeliveryDependencies) -> dict[str, Any]:
        return dependencies.daily_cup_delivery_result(
            self.sent,
            self.edited,
            self.failed,
            self.skipped,
            self.new_message_ids,
            self.replaced_message_ids,
        )


__all__ = [
    "DailyCupDeliveryContext",
    "DailyCupDeliveryDependencies",
    "DailyCupDeliveryState",
]
