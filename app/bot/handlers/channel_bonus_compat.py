from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router(name="channel_bonus_compat")

_LEGACY_CALLBACK_PREFIX = "channel_bonus:"
_LEGACY_BONUS_REMOVED_TEXT = "Dieser Bonus ist nicht mehr verfügbar."


@router.callback_query(F.data.startswith(_LEGACY_CALLBACK_PREFIX))
async def handle_legacy_channel_bonus_callback(callback: CallbackQuery) -> None:
    await callback.answer(_LEGACY_BONUS_REMOVED_TEXT, show_alert=True)
