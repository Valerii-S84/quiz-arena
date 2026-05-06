from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from app.db.models.quiz_sessions import QuizSession
from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT
from app.game.sessions.types import SessionQuestionView, StartSessionResult
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 24, 11, 0, tzinfo=UTC)
FIXED_CHALLENGE_ID = UUID("aaaaaaaa-1111-2222-3333-aaaaaaaaaaaa")
FIXED_REMATCH_ID = UUID("bbbbbbbb-1111-2222-3333-bbbbbbbbbbbb")
SERIES_ID = UUID("cccccccc-1111-2222-3333-cccccccccccc")
TOURNAMENT_MATCH_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
TOURNAMENT_ID = UUID("11111111-2222-3333-4444-555555555555")


class Session(AsyncSessionStub):
    pass


def async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def challenge(**overrides: object) -> Any:
    payload: dict[str, object] = {
        "id": uuid4(),
        "invite_token": "invite-token",
        "creator_user_id": 11,
        "opponent_user_id": 22,
        "challenge_type": DUEL_TYPE_DIRECT,
        "mode_code": "QUICK_MIX_A1A2",
        "access_type": "FREE",
        "question_ids": ["q-1", "q-2", "q-3", "q-4", "q-5"],
        "tournament_match_id": None,
        "status": DUEL_STATUS_ACCEPTED,
        "current_round": 1,
        "total_rounds": 5,
        "series_id": None,
        "series_game_number": 1,
        "series_best_of": 1,
        "creator_score": 0,
        "opponent_score": 0,
        "creator_answered_round": 0,
        "opponent_answered_round": 0,
        "winner_user_id": None,
        "creator_finished_at": None,
        "opponent_finished_at": None,
        "expires_at": NOW_UTC + timedelta(hours=1),
        "updated_at": NOW_UTC - timedelta(minutes=1),
        "completed_at": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def completed_challenge(**overrides: object) -> Any:
    payload = {
        "status": "COMPLETED",
        "current_round": 5,
        "creator_score": 3,
        "opponent_score": 2,
        "creator_answered_round": 5,
        "opponent_answered_round": 5,
        "winner_user_id": 11,
        "creator_finished_at": NOW_UTC - timedelta(minutes=2),
        "opponent_finished_at": NOW_UTC - timedelta(minutes=1),
        "completed_at": NOW_UTC - timedelta(minutes=1),
    }
    payload.update(overrides)
    return challenge(**payload)


def duel(**overrides: object) -> Any:
    payload: dict[str, object] = {
        "id": uuid4(),
        "invite_token": "new-invite-token",
        "creator_user_id": 11,
        "opponent_user_id": None,
        "challenge_type": DUEL_TYPE_DIRECT,
        "mode_code": "QUICK_MIX_A1A2",
        "access_type": "FREE",
        "question_ids": ["q-1", "q-2", "q-3", "q-4", "q-5"],
        "tournament_match_id": None,
        "status": "PENDING",
        "current_round": 1,
        "total_rounds": 5,
        "series_id": None,
        "series_game_number": 1,
        "series_best_of": 1,
        "creator_score": 0,
        "opponent_score": 0,
        "creator_answered_round": 0,
        "opponent_answered_round": 0,
        "winner_user_id": None,
        "creator_finished_at": None,
        "opponent_finished_at": None,
        "expires_at": NOW_UTC + timedelta(hours=1),
        "updated_at": NOW_UTC,
        "completed_at": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def quiz_session(*, challenge_id: UUID, user_id: int, round_no: int) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=user_id,
        source="FRIEND_CHALLENGE",
        mode_code="QUICK_MIX_A1A2",
        status="STARTED",
        energy_cost_total=0,
        question_id=f"q-{round_no}",
        friend_challenge_id=challenge_id,
        friend_challenge_round=round_no,
        started_at=NOW_UTC - timedelta(seconds=10),
        local_date_berlin=NOW_UTC.date(),
        idempotency_key=f"friend-session:{uuid4()}",
    )


def non_friend_quiz_session() -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=11,
        source="MENU",
        mode_code="QUICK_MIX_A1A2",
        status="STARTED",
        energy_cost_total=0,
        question_id="menu-q",
        friend_challenge_id=None,
        friend_challenge_round=None,
        started_at=NOW_UTC - timedelta(seconds=10),
        local_date_berlin=NOW_UTC.date(),
        idempotency_key=f"menu-session:{uuid4()}",
    )


def start_result(*, question_id: str, idempotent_replay: bool = False) -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=uuid4(),
            question_id=question_id,
            text="Question?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source="FRIEND_CHALLENGE",
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=idempotent_replay,
    )
