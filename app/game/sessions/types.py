from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class SessionQuestionView:
    session_id: UUID
    question_id: str
    text: str
    options: tuple[str, str, str, str]
    mode_code: str
    source: str
    category: str | None = None
    question_number: int | None = None
    total_questions: int | None = None


@dataclass(slots=True)
class StartSessionResult:
    session: SessionQuestionView
    energy_free: int
    energy_paid: int
    idempotent_replay: bool


@dataclass(slots=True)
class FriendChallengeSnapshot:
    challenge_id: UUID
    invite_token: str
    mode_code: str
    access_type: str
    status: str
    creator_user_id: int
    opponent_user_id: int | None
    current_round: int
    total_rounds: int
    creator_score: int
    opponent_score: int
    winner_user_id: int | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class FriendChallengeRoundStartResult:
    snapshot: FriendChallengeSnapshot
    start_result: StartSessionResult | None
    waiting_for_opponent: bool
    already_answered_current_round: bool = False


@dataclass(slots=True)
class FriendChallengeJoinResult:
    snapshot: FriendChallengeSnapshot
    joined_now: bool = False


@dataclass(slots=True)
class AnswerSessionResult:
    session_id: UUID
    question_id: str
    is_correct: bool
    current_streak: int
    best_streak: int
    idempotent_replay: bool
    mode_code: str | None = None
    source: str | None = None
    selected_answer_text: str | None = None
    correct_answer_text: str | None = None
    question_level: str | None = None
    next_preferred_level: str | None = None
    friend_challenge: FriendChallengeSnapshot | None = None
    friend_challenge_answered_round: int | None = None
    friend_challenge_round_completed: bool = False
    friend_challenge_waiting_for_opponent: bool = False
