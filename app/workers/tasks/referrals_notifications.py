from __future__ import annotations

from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.application import build_bot
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.referrals_repo import ReferralsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal


def _build_referral_reward_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=TEXTS_DE["msg.referral.reward.ready.button"],
                    callback_data="referral:open",
                )
            ]
        ]
    )


async def send_referral_rejected_notifications(*, referrer_user_ids: list[int]) -> dict[str, int]:
    if not referrer_user_ids:
        return {
            "rejected_user_notified": 0,
            "rejected_user_notify_failed": 0,
        }

    unique_ids = tuple({int(user_id) for user_id in referrer_user_ids})
    async with SessionLocal.begin() as session:
        users = await UsersRepo.list_by_ids(session, unique_ids)
    telegram_by_user_id = {int(user.id): int(user.telegram_user_id) for user in users}

    sent_total = 0
    failed_total = 0
    bot = build_bot()
    try:
        for referrer_user_id in referrer_user_ids:
            telegram_user_id = telegram_by_user_id.get(int(referrer_user_id))
            if telegram_user_id is None:
                failed_total += 1
                continue
            try:
                await bot.send_message(
                    chat_id=telegram_user_id,
                    text=TEXTS_DE["msg.referral.rejected"],
                )
                sent_total += 1
            except Exception:
                failed_total += 1
    finally:
        await bot.session.close()

    return {
        "rejected_user_notified": sent_total,
        "rejected_user_notify_failed": failed_total,
    }


async def send_referral_ready_notifications(*, notified_at: datetime) -> dict[str, int]:
    async with SessionLocal.begin() as session:
        referrer_ids = await ReferralsRepo.list_referrer_ids_with_reward_notifications(
            session,
            notified_at=notified_at,
        )
        users = await UsersRepo.list_by_ids(session, referrer_ids)

    if not users:
        return {
            "reward_user_notified": 0,
            "reward_user_notify_failed": 0,
        }

    keyboard = _build_referral_reward_ready_keyboard()
    sent_user_ids: list[int] = []
    failed_total = 0
    bot = build_bot()
    try:
        for user in users:
            try:
                await bot.send_message(
                    chat_id=int(user.telegram_user_id),
                    text=TEXTS_DE["msg.referral.reward.ready"],
                    reply_markup=keyboard,
                )
                sent_user_ids.append(int(user.id))
            except Exception:
                failed_total += 1
    finally:
        await bot.session.close()

    if sent_user_ids:
        async with SessionLocal.begin() as session:
            for user_id in sent_user_ids:
                await emit_analytics_event(
                    session,
                    event_type="referral_reward_notified",
                    source=EVENT_SOURCE_WORKER,
                    user_id=user_id,
                    payload={"notified_at": notified_at.isoformat()},
                    happened_at=notified_at,
                )

    return {
        "reward_user_notified": len(sent_user_ids),
        "reward_user_notify_failed": failed_total,
    }
