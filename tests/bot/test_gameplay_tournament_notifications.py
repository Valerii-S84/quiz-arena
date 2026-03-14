from __future__ import annotations

from app.bot.handlers import gameplay_tournament_notifications
from app.workers.tasks import daily_cup_messaging, tournaments_messaging


def test_enqueue_tournament_round_messaging_enqueues_both_workers_in_order(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        tournaments_messaging,
        "enqueue_private_tournament_round_messaging",
        lambda *, tournament_id: calls.append(("private", tournament_id)),
    )
    monkeypatch.setattr(
        daily_cup_messaging,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id: calls.append(("daily_cup", tournament_id)),
    )

    gameplay_tournament_notifications.enqueue_tournament_round_messaging(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )

    assert calls == [
        ("private", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        ("daily_cup", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    ]
