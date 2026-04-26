from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.workers.tasks import tournaments_messaging


def test_private_tournament_worker_share_url_uses_canonical_telegram_contract() -> None:
    share_url = tournaments_messaging._build_standings_share_url(
        invite_code="abcdefabcdef",
        tournament_name="Liga Finale",
    )

    parsed = urlparse(share_url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://t.me/share/url"
    assert query["url"] == ["https://t.me/Deine_Deutsch_Quiz_bot?start=tournament_abcdefabcdef"]
    assert query["text"] == ["🏆 Ich spiele im Liga Finale! Komm dazu →"]
