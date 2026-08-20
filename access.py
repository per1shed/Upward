"""Whitelist: only known team members may use the bot."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

# @Dalron_01, @per1shedcs, @vladiks5
ALLOWED_USER_IDS: frozenset[int] = frozenset(
    {
        6205102102,
        5007535736,
        1109190677,
    }
)

DENIED_TEXT = "Вы не являетесь пользователем этого бота."


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None and user.id not in ALLOWED_USER_IDS:
            if isinstance(event, Message):
                await event.answer(DENIED_TEXT)
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer(DENIED_TEXT, show_alert=True)
                except Exception:
                    pass
                if event.message:
                    try:
                        await event.message.answer(DENIED_TEXT)
                    except Exception:
                        pass
            return None
        return await handler(event, data)
