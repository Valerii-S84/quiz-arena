from urllib.parse import quote_plus

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _build_share_url(*, invite_link: str, share_text: str) -> str:
    return (
        "https://t.me/share/url" f"?url={quote_plus(invite_link)}" f"&text={quote_plus(share_text)}"
    )


def _build_share_templates(*, total_rounds: int) -> tuple[str, str, str]:
    rounds = max(1, int(total_rounds))
    return (
        f"😏 Ich fordere dich heraus! Schaffst du mehr als ich in {rounds} Fragen?",
        f"🔥 {rounds} Fragen. Gleiche Fragen. Keine Ausreden.",
        f"🏆 Quiz Arena Duell ({rounds} Fragen). Verlierer fragt nach Revanche?",
    )


def build_friend_challenge_share_url(*, base_link: str, share_text: str) -> str:
    return _build_share_url(invite_link=base_link, share_text=share_text)


def build_friend_challenge_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ SPRINT 3", callback_data="friend:challenge:create:3")],
            [InlineKeyboardButton(text="⚡ SPRINT 5", callback_data="friend:challenge:create:5")],
            [InlineKeyboardButton(text="🏆 DUELL 12", callback_data="friend:challenge:create:12")],
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )


def build_friend_challenge_next_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ NAECHSTE RUNDE", callback_data=f"friend:next:{challenge_id}"
                )
            ],
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )


def build_friend_challenge_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )


def build_friend_challenge_share_keyboard(
    *,
    invite_link: str | None,
    challenge_id: str | None,
    total_rounds: int = 12,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if invite_link:
        template_a, template_b, template_c = _build_share_templates(total_rounds=total_rounds)
        rows.append(
            [
                InlineKeyboardButton(
                    text="😏 PROVOKATION",
                    url=build_friend_challenge_share_url(
                        base_link=invite_link, share_text=template_a
                    ),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔥 GLEICHE FRAGEN",
                    url=build_friend_challenge_share_url(
                        base_link=invite_link, share_text=template_b
                    ),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🏆 REVANCHE?",
                    url=build_friend_challenge_share_url(
                        base_link=invite_link, share_text=template_c
                    ),
                )
            ]
        )
    if challenge_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="▶️ DUELL STARTEN",
                    callback_data=f"friend:next:{challenge_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_finished_keyboard(
    *,
    challenge_id: str,
    include_share: bool = True,
    show_best_of_three: bool = True,
    show_next_series_game: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🔁 REVANCHE", callback_data=f"friend:rematch:{challenge_id}")]
    ]
    if show_best_of_three:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎯 BEST OF 3",
                    callback_data=f"friend:series:best3:{challenge_id}",
                )
            ]
        )
    if show_next_series_game:
        rows.append(
            [
                InlineKeyboardButton(
                    text="▶️ NAECHSTES SPIEL",
                    callback_data=f"friend:series:next:{challenge_id}",
                )
            ]
        )
    if include_share:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📤 TEILEN",
                    callback_data=f"friend:share:result:{challenge_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_result_share_keyboard(
    *,
    share_url: str,
    challenge_id: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 JETZT TEILEN", url=share_url)],
            [
                InlineKeyboardButton(
                    text="🔁 REVANCHE", callback_data=f"friend:rematch:{challenge_id}"
                )
            ],
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )


def build_friend_challenge_limit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟 1 DUELL  |  5⭐", callback_data="buy:FRIEND_CHALLENGE_5"
                )
            ],
            [InlineKeyboardButton(text="💎 PREMIUM STARTER", callback_data="buy:PREMIUM_STARTER")],
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )
