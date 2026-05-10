from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.workers.tasks import friend_challenges_notification_content as content
from app.workers.tasks import friend_challenges_proof_card_text as card_text
from app.workers.tasks import friend_challenges_utils as utils


def test_friend_challenge_user_labels_and_captions() -> None:
    assert card_text.resolve_user_label(user=None, fallback="Spieler") == "Spieler"
    assert (
        card_text.resolve_user_label(
            user=SimpleNamespace(username="  max  ", first_name="Lea"),
            fallback="Spieler",
        )
        == "@max"
    )
    assert (
        card_text.resolve_user_label(
            user=SimpleNamespace(username="", first_name="  Lea  "),
            fallback="Spieler",
        )
        == "Lea"
    )
    assert (
        card_text.resolve_user_label(
            user=SimpleNamespace(username="", first_name=" "),
            fallback="Spieler",
        )
        == "Spieler"
    )

    creator_caption = card_text.build_caption(
        challenge_id="duel-1",
        status="COMPLETED",
        role="creator",
        creator_score=4,
        opponent_score=2,
    )
    opponent_caption = card_text.build_caption(
        challenge_id="duel-1",
        status="EXPIRED",
        role="opponent",
        creator_score=4,
        opponent_score=2,
    )
    walkover_caption = card_text.build_caption(
        challenge_id="duel-1",
        status="WALKOVER",
        role="creator",
        creator_score=4,
        opponent_score=2,
    )

    assert "DUELL ERGEBNIS" in creator_caption
    assert "Du 4 : Freund 2" in creator_caption
    assert "DUELL ABGELAUFEN" in opponent_caption
    assert "Du 2 : Freund 4" in opponent_caption
    assert "DUELL KAMPFLOS BEENDET" in walkover_caption


def test_friend_challenge_notification_text_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(content.duel_rollout, "is_canonical_duels_enabled", lambda: True)
    publish_text = content.build_unplayed_friend_challenge_text(can_publish_to_arena=True)
    assert "Arena" in publish_text

    monkeypatch.setattr(content.duel_rollout, "is_canonical_duels_enabled", lambda: False)
    wait_text = content.build_unplayed_friend_challenge_text(can_publish_to_arena=True)
    assert "schließen" in wait_text

    creator_text, opponent_text = content.build_expired_duel_texts(
        status="WALKOVER",
        creator_score=5,
        opponent_score=3,
    )
    assert "kampf" in creator_text.lower()
    assert "Du 5 | Freund 3" in creator_text
    assert "Du 3 | Freund 5" in opponent_text

    creator_text, opponent_text = content.build_expired_duel_texts(
        status="EXPIRED",
        creator_score=1,
        opponent_score=0,
    )
    assert "Zeitablauf" in creator_text
    assert "Du 0 | Freund 1" in opponent_text


def test_format_remaining_hhmm_clamps_expired_deadlines() -> None:
    now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

    assert utils.format_remaining_hhmm(now_utc=now, expires_at=now + timedelta(minutes=125)) == (
        2,
        5,
    )
    assert utils.format_remaining_hhmm(now_utc=now, expires_at=now - timedelta(seconds=1)) == (
        0,
        0,
    )
