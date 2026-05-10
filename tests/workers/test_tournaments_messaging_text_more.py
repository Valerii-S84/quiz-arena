from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from app.game.tournaments.constants import TOURNAMENT_MATCH_STATUS_PENDING
from app.workers.tasks import tournaments_messaging_text as text


def test_format_helpers_cover_empty_and_fractional_values() -> None:
    assert text.format_user_label(username="  max  ", first_name="Lea") == "@max"
    assert text.format_user_label(username=" ", first_name="  Lea  ") == "Lea"
    assert text.format_user_label(username=None, first_name=" ") == "Spieler"
    assert text.format_points(Decimal("3.000")) == "3"
    assert text.format_points(Decimal("2.500")) == "2.5"
    assert text.format_deadline(None) == "-"
    assert text.format_deadline(datetime(2026, 5, 10, 16, 30, tzinfo=UTC)) == "10.05 18:30"
    assert text.format_tournament_format("QUICK_12") == "12 Fragen"
    assert text.format_tournament_format("QUICK_5") == "5 Fragen"


def test_resolve_match_context_covers_opponent_and_non_pending_paths() -> None:
    challenge_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    playable = SimpleNamespace(
        user_a=101,
        user_b=202,
        status=TOURNAMENT_MATCH_STATUS_PENDING,
        friend_challenge_id=challenge_id,
    )
    completed = SimpleNamespace(
        user_a=101,
        user_b=303,
        status="COMPLETED",
        friend_challenge_id=None,
    )
    unrelated = SimpleNamespace(user_a=404, user_b=505, status="PENDING", friend_challenge_id=None)

    assert text.resolve_match_context(round_matches=[playable], viewer_user_id=101) == (
        str(challenge_id),
        202,
    )
    assert text.resolve_match_context(round_matches=[completed], viewer_user_id=101) == (
        None,
        303,
    )
    assert text.resolve_match_context(round_matches=[unrelated], viewer_user_id=101) == (
        None,
        None,
    )


def test_build_tournament_messages_cover_fallbacks_and_error_detection() -> None:
    standings = text.build_standings_lines(
        standings_user_ids=[1, 2, 3, 4],
        labels={1: "Lea"},
        points_by_user={1: "3"},
        viewer_user_id=2,
    )

    assert standings[0] == "1. 🥇 Lea - 3 Pkt"
    assert standings[1] == "2. 🥈 Spieler (Du) - 0 Pkt"
    assert standings[3].startswith("4.   Spieler")

    round_text = text.build_round_text(
        tournament_name=None,
        tournament_format="QUICK_12",
        round_no=1,
        deadline_text="-",
        opponent_label=None,
        standings_lines=standings[:2],
    )
    assert "🏆 Turnier mit Freunden" in round_text
    assert "Gegner: Freilos" in round_text

    completed_text = text.build_completed_text(
        tournament_name="Finale",
        tournament_format="QUICK_5",
        place=2,
        my_points="2.5",
        standings_lines=standings[:3],
    )
    assert "🏁 Turnier beendet!" in completed_text
    assert "Dein Ergebnis: Platz #2 • 2.5 Pkt" in completed_text

    assert text.is_message_not_modified_error(Exception("Bad Request: message is not modified"))
    assert not text.is_message_not_modified_error(Exception("other"))
