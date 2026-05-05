import pytest

from app.game.duels.constants import (
    DUEL_CAN_SELECT_LEVEL,
    DUEL_CAN_SELECT_QUESTION_COUNT,
    DUEL_CAN_SELECT_TOPIC,
    DUEL_FREE_LIMITS_PER_DAY,
    DUEL_LIMIT_ACTION_ARENA_ACCEPT,
    DUEL_LIMIT_ACTION_ARENA_CREATE,
    DUEL_LIMIT_ACTION_FRIEND_CREATE,
    DUEL_LIMIT_ACTION_REVANCHE,
    DUEL_MODE_ARENA,
    DUEL_MODE_FRIEND,
    DUEL_PAYWALL_PRODUCT_CODES,
    DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE,
    DUEL_PREMIUM_WEEK_PRODUCT_CODE,
    DUEL_QUESTION_COUNT,
    DUEL_TICKET_PRODUCT_CODE,
)
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.service.constants import FRIEND_CHALLENGE_TOTAL_ROUNDS
from app.game.sessions.service.friend_challenges_question_plan import resolve_duel_rounds


def test_duels_product_contract_has_two_modes_and_fixed_question_count() -> None:
    assert (DUEL_MODE_ARENA, DUEL_MODE_FRIEND) == ("OFFENE_ARENA", "FREUNDESDUELL")
    assert DUEL_QUESTION_COUNT == 7
    assert FRIEND_CHALLENGE_TOTAL_ROUNDS == DUEL_QUESTION_COUNT
    assert DUEL_CAN_SELECT_TOPIC is False
    assert DUEL_CAN_SELECT_LEVEL is False
    assert DUEL_CAN_SELECT_QUESTION_COUNT is False


def test_duels_friend_round_contract_accepts_only_seven_questions() -> None:
    assert resolve_duel_rounds(total_rounds=7) == DUEL_QUESTION_COUNT

    for legacy_rounds in (5, 12):
        with pytest.raises(FriendChallengeAccessError):
            resolve_duel_rounds(total_rounds=legacy_rounds)


def test_duels_paywall_contract_excludes_premium_three_days() -> None:
    assert DUEL_PAYWALL_PRODUCT_CODES == ("FRIEND_CHALLENGE_5", "PREMIUM_WEEK")
    assert DUEL_TICKET_PRODUCT_CODE == "FRIEND_CHALLENGE_5"
    assert DUEL_PREMIUM_WEEK_PRODUCT_CODE == "PREMIUM_WEEK"
    assert DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE == "PREMIUM_3_DAYS"
    assert DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE not in DUEL_PAYWALL_PRODUCT_CODES


def test_duels_free_limits_contract() -> None:
    assert DUEL_FREE_LIMITS_PER_DAY == {
        DUEL_LIMIT_ACTION_ARENA_ACCEPT: 3,
        DUEL_LIMIT_ACTION_ARENA_CREATE: 1,
        DUEL_LIMIT_ACTION_FRIEND_CREATE: 2,
        DUEL_LIMIT_ACTION_REVANCHE: 1,
    }
