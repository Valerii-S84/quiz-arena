from __future__ import annotations

from app.core.config import settings

TOURNAMENT_TYPE_PRIVATE = "PRIVATE"
TOURNAMENT_TYPE_DAILY_ARENA = "DAILY_ARENA"
TOURNAMENT_TYPE_DAILY_ELIMINATION = "DAILY_ELIMINATION"
DAILY_CUP_TOURNAMENT_TYPES = frozenset(
    {
        TOURNAMENT_TYPE_DAILY_ARENA,
        TOURNAMENT_TYPE_DAILY_ELIMINATION,
    }
)

TOURNAMENT_STATUS_REGISTRATION = "REGISTRATION"
TOURNAMENT_STATUS_ROUND_1 = "ROUND_1"
TOURNAMENT_STATUS_ROUND_2 = "ROUND_2"
TOURNAMENT_STATUS_ROUND_3 = "ROUND_3"
TOURNAMENT_STATUS_ROUND_4 = "ROUND_4"
TOURNAMENT_STATUS_BRACKET_LIVE = "BRACKET_LIVE"
TOURNAMENT_STATUS_COMPLETED = "COMPLETED"
TOURNAMENT_STATUS_CANCELED = "CANCELED"

TOURNAMENT_MATCH_STATUS_PENDING = "PENDING"
TOURNAMENT_MATCH_STATUS_COMPLETED = "COMPLETED"
TOURNAMENT_MATCH_STATUS_WALKOVER = "WALKOVER"

TOURNAMENT_FORMAT_QUICK_5 = "QUICK_5"
TOURNAMENT_FORMAT_QUICK_12 = "QUICK_12"

TOURNAMENT_MODE_CODE = "QUICK_MIX_A1A2"
TOURNAMENT_SELF_BOT_LABEL = "Arena Bot"
TOURNAMENT_SELF_BOT_DEFAULT_CORRECT_ANSWERS = 2
TOURNAMENT_MAX_ROUNDS = max(1, int(settings.tournament_rounds))
TOURNAMENT_DEFAULT_MAX_PARTICIPANTS = max(2, int(settings.tournament_max_participants))
TOURNAMENT_MIN_PARTICIPANTS = max(2, int(settings.tournament_min_participants))
TOURNAMENT_DEFAULT_REGISTRATION_HOURS = max(1, int(settings.tournament_round_ttl_hours))
TOURNAMENT_DEFAULT_ROUND_DURATION_HOURS = max(1, int(settings.tournament_round_ttl_hours))
DAILY_CUP_MAX_ROUNDS_SMALL = 3
DAILY_CUP_MAX_ROUNDS_LARGE = 4
DAILY_CUP_QUESTIONS_PER_MATCH = 7
DAILY_CUP_MAX_PARTICIPANTS = 100


def daily_cup_max_rounds_for_participants(*, participants_total: int) -> int:
    if int(participants_total) >= 21:
        return DAILY_CUP_MAX_ROUNDS_LARGE
    return DAILY_CUP_MAX_ROUNDS_SMALL


def rounds_for_tournament_format(*, format_code: str) -> int:
    if format_code == TOURNAMENT_FORMAT_QUICK_5:
        return 5
    if format_code == TOURNAMENT_FORMAT_QUICK_12:
        return 12
    raise ValueError(format_code)


def status_for_round(*, round_no: int) -> str:
    if round_no == 1:
        return TOURNAMENT_STATUS_ROUND_1
    if round_no == 2:
        return TOURNAMENT_STATUS_ROUND_2
    if round_no == 3:
        return TOURNAMENT_STATUS_ROUND_3
    if round_no == 4:
        return TOURNAMENT_STATUS_ROUND_4
    raise ValueError(round_no)
