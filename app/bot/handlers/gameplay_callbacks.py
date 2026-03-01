from __future__ import annotations

import re
from uuid import UUID

ANSWER_RE = re.compile(r"^answer:([0-9a-f\-]{36}):([0-3])$")
STOP_RE = re.compile(r"^game:stop:([0-9a-f\-]{36})$")
FRIEND_NEXT_RE = re.compile(r"^friend:next:([0-9a-f\-]{36})$")
FRIEND_CREATE_TYPE_RE = re.compile(r"^friend:challenge:type:(direct|open|tournament)$")
FRIEND_CREATE_FORMAT_RE = re.compile(r"^friend:challenge:format:(direct|open):(5|12)$")
FRIEND_CREATE_LEGACY_RE = re.compile(r"^friend:challenge:create:(5|12)$")
FRIEND_REMATCH_RE = re.compile(r"^friend:rematch:([0-9a-f\-]{36})$")
FRIEND_SHARE_RESULT_RE = re.compile(r"^friend:share:result:([0-9a-f\-]{36})$")
FRIEND_SERIES_BEST3_RE = re.compile(r"^friend:series:best3:([0-9a-f\-]{36})$")
FRIEND_SERIES_NEXT_RE = re.compile(r"^friend:series:next:([0-9a-f\-]{36})$")
FRIEND_COPY_LINK_RE = re.compile(r"^friend:copy:([0-9a-f\-]{36})$")
FRIEND_OPEN_REPOST_RE = re.compile(r"^friend:open:repost:([0-9a-f\-]{36})$")
FRIEND_DELETE_RE = re.compile(r"^friend:delete:([0-9a-f\-]{36})$")
TOURNAMENT_FORMAT_RE = re.compile(r"^friend:tournament:format:(5|12)$")
TOURNAMENT_JOIN_RE = re.compile(r"^friend:tournament:join:([a-f0-9]{12})$", re.IGNORECASE)
TOURNAMENT_COPY_LINK_RE = re.compile(r"^friend:tournament:copy:([0-9a-f\-]{36})$")
TOURNAMENT_START_RE = re.compile(r"^friend:tournament:start:([0-9a-f\-]{36})$")
TOURNAMENT_VIEW_RE = re.compile(r"^friend:tournament:view:([0-9a-f\-]{36})$")
TOURNAMENT_SHARE_RE = re.compile(r"^friend:tournament:share:([0-9a-f\-]{36})$")
DAILY_CUP_JOIN_RE = re.compile(r"^daily:cup:join:([0-9a-f\-]{36})$")
DAILY_CUP_VIEW_RE = re.compile(r"^daily:cup:view:([0-9a-f\-]{36})$")
DAILY_CUP_SHARE_RE = re.compile(r"^daily:cup:share:([0-9a-f\-]{36})$")
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


def parse_friend_create_format(callback_data: str) -> tuple[str, int] | None:
    """Parses friend challenge format callback into type and rounds."""

    matched = FRIEND_CREATE_FORMAT_RE.match(callback_data)
    if matched is None:
        return None
    return matched.group(1), int(matched.group(2))


def parse_challenge_rounds(callback_data: str) -> int | None:
    """Legacy parser kept for backward compatibility with older callbacks/tests."""

    legacy_match = FRIEND_CREATE_LEGACY_RE.match(callback_data)
    if legacy_match is not None:
        return int(legacy_match.group(1))
    parsed = parse_friend_create_format(callback_data)
    if parsed is None:
        return None
    return parsed[1]


def parse_uuid_callback(*, pattern: re.Pattern[str], callback_data: str) -> UUID | None:
    """Extracts UUID payload from callback matched by the provided regex pattern."""

    matched = pattern.match(callback_data)
    if matched is None:
        return None
    return UUID(matched.group(1))


def parse_tournament_format(callback_data: str) -> int | None:
    matched = TOURNAMENT_FORMAT_RE.match(callback_data)
    if matched is None:
        return None
    return int(matched.group(1))


def parse_tournament_invite_code(callback_data: str) -> str | None:
    matched = TOURNAMENT_JOIN_RE.match(callback_data)
    if matched is None:
        return None
    return matched.group(1).lower()


def parse_mode_code(callback_data: str) -> str:
    """Returns mode code from `mode:<mode_code>` callback payload."""

    return callback_data.split(":", maxsplit=1)[1]
