from __future__ import annotations

REQUIRED_COLUMNS = [
    "quiz_id",
    "question",
    "option_1",
    "option_2",
    "option_3",
    "option_4",
    "correct_option_id",
    "correct_answer",
    "explanation",
    "key",
    "level",
    "category",
]

OPTION_COLUMNS = ["option_1", "option_2", "option_3", "option_4"]
TEXT_CHECK_COLUMNS = [
    "question",
    "option_1",
    "option_2",
    "option_3",
    "option_4",
    "correct_answer",
    "explanation",
    "key",
]
DATE_COLUMNS = ["created_at", "published_at"]
