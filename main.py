import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.types import MenuButtonCommands

from access import AccessMiddleware, PASHOK_ID
from config import load_settings
from database import fill_all_missed_days, init_db
from handlers import router
from pavel_handlers import router as pavel_router
from timezone_utils import TZ


def setup_logging() -> None:
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("aiogram").setLevel(logging.ERROR)


async def run_bot() -> None:
    settings = load_settings()
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())
    dp.include_router(pavel_router)
    dp.include_router(router)

    me = await bot.get_me()
    await fill_all_missed_days()
    try:
        await bot.set_chat_menu_button(chat_id=PASHOK_ID, menu_button=MenuButtonCommands())
    except Exception:
        logging.getLogger("upward").exception("menu button")
    print(f"🚀 Бот @{me.username} запущен ({TZ})")

    async def auto_zero_loop() -> None:
        while True:
            await asyncio.sleep(3600)
            await fill_all_missed_days()

    task = asyncio.create_task(auto_zero_loop())

    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        task.cancel()
        await bot.session.close()


def main() -> None:
    setup_logging()
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"❌ Ошибка: {exc}", file=sys.stderr)
        sys.exit(1)
    print("🛑 Бот остановлен")


if __name__ == "__main__":
    main()
