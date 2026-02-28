"""Точка входа — aiogram 3.x polling."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config.settings import settings
from bot.handlers import calculator, common, consultant, documents
from bot.middlewares.access import AccessMiddleware


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Middleware — whitelist по chat_id
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    # Роутеры (порядок важен: consultant последний — ловит свободный текст)
    dp.include_routers(
        common.router,
        calculator.router,
        documents.router,
        consultant.router,
    )

    logging.info("Бот-бухгалтер запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
