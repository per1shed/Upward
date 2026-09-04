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

DISPLAY_NAMES: dict[int, str] = {
    6205102102: "Диман",
    5007535736: "Пашок",
    1109190677: "Владос",
}

# Диман → Пашок → Владос
USER_ORDER: tuple[int, ...] = (
    6205102102,
    5007535736,
    1109190677,
)

# Фиксированные цвета участников (не зависят от порядка в списке)
USER_COLORS: dict[int, str] = {
    6205102102: "#0A84FF",  # Диман — синий
    5007535736: "#FF9F0A",  # Пашок — оранжевый
    1109190677: "#30D158",  # Владос — зелёный
}

_FALLBACK_COLORS: tuple[str, ...] = (
    "#0A84FF",
    "#FF9F0A",
    "#30D158",
    "#5E5CE6",
    "#FF375F",
    "#64D2FF",
)

_USER_ORDER_INDEX = {uid: i for i, uid in enumerate(USER_ORDER)}


def display_name_for(user_id: int, fallback: str = "") -> str:
    return DISPLAY_NAMES.get(user_id) or fallback


def color_for(user_id: int, fallback_index: int = 0) -> str:
    if user_id in USER_COLORS:
        return USER_COLORS[user_id]
    return _FALLBACK_COLORS[fallback_index % len(_FALLBACK_COLORS)]


def sort_users(users: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Sort users: Диман, Пашок, Владос, then others by id."""
    return sorted(
        users,
        key=lambda row: (_USER_ORDER_INDEX.get(row[0], len(USER_ORDER)), row[0]),
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
