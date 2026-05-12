from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TournamentProofCardContextRequest:
    session: Any
    parsed_tournament_id: UUID
    user_id: int | None


@dataclass(frozen=True, slots=True)
class TournamentProofCardContextServices:
    tournaments_repo: Any
    participants_repo: Any
    users_repo: Any
    format_points_fn: Callable[..., str]
    format_tournament_format_fn: Callable[..., str]
    format_user_label_fn: Callable[..., str]


@dataclass(frozen=True, slots=True)
class TournamentProofCardContext:
    parsed_tournament_id: UUID
    tournament: Any
    participants: list[Any]
    participants_total: int
    tournament_format: str
    standings_user_ids: list[int]
    points_by_user: dict[int, str]
    telegram_targets: dict[int, int]
    user_labels: dict[int, str]


@dataclass(frozen=True, slots=True)
class TournamentProofCardDeliveryResult:
    sent: int
    cached_reused: int
    failed: int


@dataclass(frozen=True, slots=True)
class TournamentProofCardDeliveryRequest:
    context: TournamentProofCardContext
    tournament_id: str
    now_utc: datetime
    explicit_resend: bool
    lock_retry_attempt: int = 0
    retry_delay_seconds: int = 2


@dataclass(frozen=True, slots=True)
class TournamentProofCardDeliveryServices:
    session_factory: Any
    participants_repo: Any
    build_bot_fn: Callable[[], Any]
    build_caption_fn: Callable[..., str]
    render_card_fn: Callable[..., bytes]
    logger: Any
    enqueue_retry_fn: Callable[..., bool] | None = None


@dataclass(frozen=True, slots=True)
class TournamentProofCardAttemptResult:
    sent: bool
    cached_reused: bool
    failed: bool
    retry_needed: bool = False
