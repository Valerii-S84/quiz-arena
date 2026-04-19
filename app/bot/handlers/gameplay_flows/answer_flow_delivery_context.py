from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.game.sessions.types import AnswerSessionResult


class PostGamePromptLike(Protocol):
    @property
    def show_channel_bonus_prompt(self) -> bool: ...

    @property
    def show_referral_prompt(self) -> bool: ...


class SubmittedAnswerLike(Protocol):
    @property
    def now_utc(self) -> datetime: ...

    @property
    def result(self) -> AnswerSessionResult: ...

    @property
    def post_game_prompt(self) -> PostGamePromptLike: ...


class AnswerFlowDeliveryDeps(Protocol):
    session_local: Any
    user_onboarding_service: Any
    game_session_service: Any
    channel_bonus_service: Any
    offer_service: Any
    offer_logging_error: Any
    build_question_text: Any
    continue_regular_mode_after_answer: Any
    handle_daily_answer_branch: Any
    handle_friend_answer_branch: Any
    resolve_opponent_label: Any
    notify_opponent: Any
    friend_opponent_user_id: Any
    build_friend_score_text: Any
    build_friend_ttl_text: Any
    build_friend_finish_text: Any
    build_public_badge_label: Any
    build_friend_proof_card_text: Any
    enqueue_friend_challenge_proof_cards: Any
    build_series_progress_text: Any
    send_friend_round_question: Any
