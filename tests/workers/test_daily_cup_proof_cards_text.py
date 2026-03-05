from app.workers.tasks.daily_cup_proof_cards_text import build_caption


def test_build_caption_includes_bot_link() -> None:
    caption = build_caption(place=3, points="2.5")

    assert "Daily Arena Cup" in caption
    assert "Platz #3" in caption
    assert "Punkte: 2.5" in caption
    assert "https://t.me/Deine_Deutsch_Quiz_bot" in caption
