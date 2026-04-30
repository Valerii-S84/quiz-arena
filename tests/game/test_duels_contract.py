from app.game.duels.constants import (
    DUEL_CAN_SELECT_LEVEL,
    DUEL_CAN_SELECT_QUESTION_COUNT,
    DUEL_CAN_SELECT_TOPIC,
    DUEL_MODE_ARENA,
    DUEL_MODE_FRIEND,
    DUEL_PAYWALL_PRODUCT_CODES,
    DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE,
    DUEL_QUESTION_COUNT,
)


def test_duels_product_contract_has_two_modes_and_fixed_question_count() -> None:
    assert (DUEL_MODE_ARENA, DUEL_MODE_FRIEND) == ("OFFENE_ARENA", "FREUNDESDUELL")
    assert DUEL_QUESTION_COUNT == 7
    assert DUEL_CAN_SELECT_TOPIC is False
    assert DUEL_CAN_SELECT_LEVEL is False
    assert DUEL_CAN_SELECT_QUESTION_COUNT is False


def test_duels_paywall_contract_excludes_premium_three_days() -> None:
    assert DUEL_PAYWALL_PRODUCT_CODES == ("FRIEND_CHALLENGE_5", "PREMIUM_WEEK")
    assert DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE == "PREMIUM_3_DAYS"
    assert DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE not in DUEL_PAYWALL_PRODUCT_CODES
