from __future__ import annotations

import re
from uuid import UUID

ANSWER_RE = re.compile(r"^answer:([0-9a-f\-]{36}):([0-3])$")
STOP_RE = re.compile(r"^game:stop:([0-9a-f\-]{36})$")
FRIEND_NEXT_RE = re.compile(r"^friend:next:([0-9a-f\-]{36})$")
FRIEND_CREATE_RE = re.compile(r"^friend:challenge:create:(3|5|12)$")
FRIEND_REMATCH_RE = re.compile(r"^friend:rematch:([0-9a-f\-]{36})$")
FRIEND_SHARE_RESULT_RE = re.compile(r"^friend:share:result:([0-9a-f\-]{36})$")
FRIEND_SERIES_BEST3_RE = re.compile(r"^friend:series:best3:([0-9a-f\-]{36})$")
FRIEND_SERIES_NEXT_RE = re.compile(r"^friend:series:next:([0-9a-f\-]{36})$")
DAILY_RESULT_RE = re.compile(r"^daily:result:([0-9a-f\-]{36})$")


def parse_answer_callback(callback_data: str) -> tuple[UUID, int] | None:
    """Parses answer callback payload into session UUID and selected option index."""

    matched = ANSWER_RE.match(callback_data)
    if matched is None:
        return None
    return UUID(matched.group(1)), int(matched.group(2))


def parse_stop_callback(callback_data: str) -> UUID | None:
    """Parses stop callback payload into session UUID."""

    matched = STOP_RE.match(callback_data)
    if matched is None:
        return None
    return UUID(matched.group(1))


def parse_challenge_rounds(callback_data: str) -> int | None:
    """Parses friend challenge rounds payload."""

    matched = FRIEND_CREATE_RE.match(callback_data)
    if matched is None:
        return None
    return int(matched.group(1))


def parse_uuid_callback(*, pattern: re.Pattern[str], callback_data: str) -> UUID | None:
    """Extracts UUID payload from callback matched by the provided regex pattern."""

    matched = pattern.match(callback_data)
    if matched is None:
        return None
    return UUID(matched.group(1))


def parse_mode_code(callback_data: str) -> str:
    """Returns mode code from `mode:<mode_code>` callback payload."""

    return callback_data.split(":", maxsplit=1)[1]
