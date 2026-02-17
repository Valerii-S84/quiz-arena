import asyncio

from app.bot.application import build_bot, build_dispatcher


async def main() -> None:
    bot = build_bot()
    dp = build_dispatcher()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
