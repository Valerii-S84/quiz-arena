from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.game.sessions.types import FriendChallengeSnapshot


@dataclass(frozen=True, slots=True)
class ArenaRevancheContext:
    arena_duel_id: UUID
    source_attempt_id: UUID
    sender_user_id: int
    receiver_user_id: int
    mode_code: str


@dataclass(frozen=True, slots=True)
class ArenaRevancheRequest:
    context: ArenaRevancheContext
    challenge: FriendChallengeSnapshot | None
    already_sent: bool = False
