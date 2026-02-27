from app.bot.keyboards.daily import build_daily_push_keyboard, build_daily_result_keyboard
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_create_keyboard,
    build_friend_challenge_format_keyboard,
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_pending_expired_keyboard,
    build_friend_open_taken_keyboard,
    build_friend_challenge_result_share_keyboard,
    build_friend_challenge_share_keyboard,
    build_friend_challenge_share_url,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.promo import build_promo_discount_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.keyboards.referral import build_referral_keyboard

__all__ = [
    "build_home_keyboard",
    "build_daily_push_keyboard",
    "build_daily_result_keyboard",
    "build_friend_challenge_create_keyboard",
    "build_friend_challenge_format_keyboard",
    "build_friend_challenge_back_keyboard",
    "build_friend_challenge_finished_keyboard",
    "build_friend_challenge_limit_keyboard",
    "build_friend_challenge_next_keyboard",
    "build_friend_pending_expired_keyboard",
    "build_friend_open_taken_keyboard",
    "build_friend_challenge_result_share_keyboard",
    "build_friend_challenge_share_keyboard",
    "build_friend_challenge_share_url",
    "build_offer_keyboard",
    "build_promo_discount_keyboard",
    "build_quiz_keyboard",
    "build_referral_keyboard",
]
