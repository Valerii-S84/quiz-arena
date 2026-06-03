from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.promo_callbacks import build_promo_open_callback_data, generate_promo_menu_nonce


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _row(text: str, callback_data: str) -> list[InlineKeyboardButton]:
    return [_button(text, callback_data)]


def _channel_bonus_row(*, channel_bonus_claimed: bool) -> list[InlineKeyboardButton]:
    if channel_bonus_claimed:
        return _row("✅ Kanal-Bonus bereits erhalten", "channel_bonus:claimed")
    return _row("📺 Kanal abonnieren → volle Energie", "channel_bonus:open")


def build_shop_keyboard(
    *,
    channel_bonus_claimed: bool = False,
    promo_nonce: str | None = None,
) -> InlineKeyboardMarkup:
    resolved_promo_nonce = promo_nonce or generate_promo_menu_nonce()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _row("⚡ Energie +10 | 5⭐", "buy:ENERGY_10"),
            _row("⚔️ Duell-Ticket | 5⭐", "buy:FRIEND_CHALLENGE_5"),
            _row("💎 Premium Woche | 29⭐", "buy:PREMIUM_WEEK"),
            _row("💎 Premium Monat | 99⭐", "buy:PREMIUM_MONTH"),
            _row("💎 Premium Saison | 249⭐", "buy:PREMIUM_SEASON"),
            _row("💎 Premium Jahr | 499⭐", "buy:PREMIUM_YEAR"),
            _channel_bonus_row(channel_bonus_claimed=channel_bonus_claimed),
            _row("👥 Freunde einladen → Belohnung", "referral:open"),
            _row("🎟️ Promo-Code eingeben", build_promo_open_callback_data(resolved_promo_nonce)),
            _row("⬅️ Zurück", "home:open"),
        ]
    )
