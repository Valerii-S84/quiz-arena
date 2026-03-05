from types import SimpleNamespace

from app.workers.tasks import daily_cup_turn_reminder


def test_resolve_turn_reminder_users_for_creator_done() -> None:
    challenge = SimpleNamespace(
        status="CREATOR_DONE",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ((22, 10),)


def test_resolve_turn_reminder_users_for_opponent_done() -> None:
    challenge = SimpleNamespace(
        status="OPPONENT_DONE",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ((10, 22),)


def test_resolve_turn_reminder_users_for_accepted_returns_both_users() -> None:
    challenge = SimpleNamespace(
        status="ACCEPTED",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ((10, 22), (22, 10))


def test_resolve_turn_reminder_users_returns_empty_for_other_status() -> None:
    challenge = SimpleNamespace(
        status="PENDING",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ()
