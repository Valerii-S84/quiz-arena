from __future__ import annotations

from pathlib import Path

from app.game.arena_duels import analytics as duel_analytics
from app.game.arena_duels import constants as arena_constants

EXPECTED_CANONICAL_DUEL_EVENTS = frozenset(
    {
        "duel_menu_opened",
        "duel_mode_selected",
        "arena_opened",
        "arena_duel_created",
        "arena_duel_started",
        "arena_duel_completed",
        "arena_duel_published",
        "arena_duel_accepted",
        "arena_result_shown",
        "arena_result_beaten_notification_sent",
        "arena_revanche_clicked",
        "friend_duel_opened",
        "friend_duel_created",
        "friend_duel_share_clicked",
        "friend_duel_joined",
        "friend_duel_started",
        "friend_duel_completed",
        "friend_duel_published_to_arena",
        "friend_duel_revanche_clicked",
        "duel_limit_hit",
        "duel_paywall_shown",
        "duel_ticket_clicked",
        "premium_week_clicked",
        "purchase_credited",
    }
)

LEGACY_FRIEND_DUEL_EVENTS = frozenset(
    {
        "friend_challenge_created",
        "friend_challenge_joined",
        "duel_created",
        "duel_accepted",
        "duel_completed",
        "duel_reposted_as_open",
        "duel_revanche_created",
        "duel_share_clicked",
    }
)


def _exported_event_values() -> set[str]:
    values: set[str] = set()
    for module in (duel_analytics, arena_constants):
        for name, value in vars(module).items():
            if not isinstance(value, str):
                continue
            if name.startswith("ARENA_EVENT_") or name.endswith("_EVENT"):
                values.add(value)
    values.add("purchase_credited")
    return values


def test_duel_analytics_code_exports_canonical_vision_events() -> None:
    exported_events = _exported_event_values()

    assert EXPECTED_CANONICAL_DUEL_EVENTS <= exported_events
    assert not (LEGACY_FRIEND_DUEL_EVENTS & exported_events)


def test_duel_analytics_catalog_matches_canonical_vision_events() -> None:
    catalog = Path("docs/analytics/events_catalog.md").read_text(encoding="utf-8")

    for event_name in EXPECTED_CANONICAL_DUEL_EVENTS:
        assert f"`{event_name}`" in catalog
    for legacy_event_name in LEGACY_FRIEND_DUEL_EVENTS:
        assert f"`{legacy_event_name}`" not in catalog
