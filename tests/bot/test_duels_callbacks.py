from uuid import UUID

from app.bot.handlers import gameplay_callbacks


def test_friend_format_parser_keeps_legacy_formats_and_accepts_clean_seven() -> None:
    assert gameplay_callbacks.parse_friend_create_format("friend:challenge:format:direct:5") == (
        "direct",
        5,
    )
    assert gameplay_callbacks.parse_friend_create_format("friend:challenge:format:direct:12") == (
        "direct",
        12,
    )
    assert gameplay_callbacks.parse_friend_create_format("friend:challenge:format:direct:7") == (
        "direct",
        7,
    )


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


def test_arena_publish_friend_rejects_malformed_uuid() -> None:
    malformed_payloads = [
        "arena:publish_friend:not-a-uuid",
        "arena:publish_friend:00000000000000000000000000000001",
        "arena:publish_friend:00000000-0000-0000-0000-00000000000g",
        "arena:publish_friend:00000000-0000-0000-0000-000000000001:extra",
    ]
    for payload in malformed_payloads:
        assert (
            gameplay_callbacks.parse_uuid_callback(
                pattern=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
                callback_data=payload,
            )
            is None
        )
