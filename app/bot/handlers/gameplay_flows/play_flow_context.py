from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

BuildQuestionText = Callable[..., str]
EnergyHandler = Callable[..., Awaitable[None]]
HomeKeyboardFactory = Callable[[], Any]


@dataclass(frozen=True)
class StartModeFlowServices:
    session_local: Any
    user_onboarding_service: Any
    game_session_service: Any
    offer_service: Any
    offer_logging_error: type[Exception]
    channel_bonus_service: Any
    build_question_text: BuildQuestionText
    energy_handler: EnergyHandler
    home_keyboard_factory: HomeKeyboardFactory


@dataclass(frozen=True)
class ContinueModeFlowServices:
    session_local: Any
    user_onboarding_service: Any
    game_session_service: Any
    offer_service: Any
    offer_logging_error: type[Exception]
    channel_bonus_service: Any
    build_question_text: BuildQuestionText
    energy_handler: EnergyHandler
    event_logger: Any
