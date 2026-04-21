from app.bot.texts.de import TEXTS_DE


def test_shop_title_explains_premium_benefits() -> None:
    shop_title = TEXTS_DE["msg.shop.title"]

    assert "Premium bringt dir" in shop_title
    assert "unbegrenzte Duelle" in shop_title
    assert "ohne Energie-Pausen" in shop_title
    assert "sparen Sterne" in shop_title


def test_offer_dismiss_copy_matches_shorter_mute_window() -> None:
    assert "24 Stunden" in TEXTS_DE["msg.offer.dismissed"]
