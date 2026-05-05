from uuid import UUID

import pytest

from app.bot.handlers import gameplay_callbacks


def test_friend_format_parser_accepts_only_canonical_friend_duel_entry_in_contract_tests() -> None:
    assert gameplay_callbacks.parse_friend_create_format("friend:challenge:format:direct:7") == (
        "direct",
        7,
    )


def test_challenge_rounds_parser_returns_canonical_seven_questions() -> None:
    assert gameplay_callbacks.parse_challenge_rounds("friend:challenge:format:direct:7") == 7


@pytest.mark.parametrize(
    "callback_data",
    [
        "friend:challenge:format:direct:5",
        "friend:challenge:format:direct:12",
        "friend:challenge:format:open:5",
        "friend:challenge:format:open:7",
        "friend:challenge:format:open:12",
        "friend:challenge:create:5",
        "friend:challenge:create:12",
    ],
)
def test_friend_format_parser_rejects_legacy_non_seven_create_paths(
    callback_data: str,
) -> None:
    assert gameplay_callbacks.parse_friend_create_format(callback_data) is None
    assert gameplay_callbacks.parse_challenge_rounds(callback_data) is None


@pytest.mark.parametrize(
    ("pattern_name", "callback_data"),
    [
        ("FRIEND_CREATE_TYPE_RE", "friend:challenge:type:direct"),
        ("FRIEND_CREATE_TYPE_RE", "friend:challenge:type:open"),
        ("FRIEND_CREATE_TYPE_RE", "friend:challenge:type:tournament"),
        ("FRIEND_OPEN_REPOST_RE", "friend:open:repost:00000000-0000-0000-0000-000000000001"),
        ("FRIEND_SERIES_BEST3_RE", "friend:series:best3:00000000-0000-0000-0000-000000000001"),
        ("TOURNAMENT_FORMAT_RE", "friend:tournament:format:5"),
        ("TOURNAMENT_FORMAT_RE", "friend:tournament:format:12"),
        (
            "TOURNAMENT_CREATE_FOR_VIEW_RE",
            "friend:tournament:create:00000000-0000-0000-0000-000000000001",
        ),
        ("TOURNAMENT_VIEW_RE", "friend:tournament:view:00000000-0000-0000-0000-000000000001"),
    ],
)
def test_duelle_callback_contract_has_no_open_series_or_tournament_leakage(
    pattern_name: str,
    callback_data: str,
) -> None:
    pattern = getattr(gameplay_callbacks, pattern_name)

    assert pattern.match(callback_data) is None


def test_arena_uuid_callbacks_are_declared() -> None:
    challenge_id = "00000000-0000-0000-0000-000000000001"
    assert gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.ARENA_ACCEPT_RE,
        callback_data=f"arena:accept:{challenge_id}",
    ) == UUID(challenge_id)
    assert gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.ARENA_START_ATTEMPT_RE,
        callback_data=f"arena:start_attempt:{challenge_id}",
    ) == UUID(challenge_id)
    assert gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        callback_data=f"arena:publish_friend:{challenge_id}",
    ) == UUID(challenge_id)
    assert gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.ARENA_REVANCHE_RE,
        callback_data=f"arena:revanche:{challenge_id}",
    ) == UUID(challenge_id)
    assert gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.ARENA_REVANCHE_SEND_RE,
        callback_data=f"arena:revanche_send:{challenge_id}",
    ) == UUID(challenge_id)
    assert gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.ARENA_CHALLENGE_FRIEND_RE,
        callback_data=f"arena:challenge_friend:{challenge_id}",
    ) == UUID(challenge_id)


def test_arena_publish_friend_rejects_malformed_uuid() -> None:
    malformed_payloads = [
        "arena:publish_friend:not-a-uuid",
        "arena:publish_friend:00000000000000000000000000000001",
        "arena:publish_friend:00000000-0000-0000-0000-00000000000g",
        "arena:publish_friend:00000000-0000-0000-0000-000000000001:extra",
        "arena:revanche:not-a-uuid",
        "arena:revanche:00000000000000000000000000000001",
        "arena:revanche_send:not-a-uuid",
        "arena:revanche_send:00000000-0000-0000-0000-000000000001:extra",
    ]
    for payload in malformed_payloads:
        publish_result = gameplay_callbacks.parse_uuid_callback(
            pattern=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
            callback_data=payload,
        )
        revanche_result = gameplay_callbacks.parse_uuid_callback(
            pattern=gameplay_callbacks.ARENA_REVANCHE_RE,
            callback_data=payload,
        )
        send_result = gameplay_callbacks.parse_uuid_callback(
            pattern=gameplay_callbacks.ARENA_REVANCHE_SEND_RE,
            callback_data=payload,
        )
        assert publish_result is None
        assert revanche_result is None
        assert send_result is None
