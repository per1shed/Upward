from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from timezone_utils import today_local

MONTH_NAMES = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅отметить", callback_data="menu:log"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
    )
    return builder.as_markup()


def chart_nav_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month + 1 if month < 12 else 1
    next_year = year + 1 if month == 12 else year
    today = today_local()

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="◀️",
            callback_data=f"chart:nav:{prev_year}-{prev_month:02d}",
        ),
        InlineKeyboardButton(
            text=MONTH_NAMES[month]
            if year == today.year
            else f"{MONTH_NAMES[month]} {year}",
            callback_data=f"chart:nav:{year}-{month:02d}",
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=f"chart:nav:{next_year}-{next_month:02d}",
        ),
    )
    builder.row(InlineKeyboardButton(text="« Меню", callback_data="menu:home"))
    builder.row(
        InlineKeyboardButton(
            text="⭐ Календарь прорывов",
            callback_data=f"chart:breakthroughs:{year}",
        )
    )
    return builder.as_markup()


def breakthrough_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="◀️",
            callback_data=f"chart:breakthroughs:{year - 1}",
        ),
        InlineKeyboardButton(
            text=str(year),
            callback_data=f"chart:breakthroughs:{year}",
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=f"chart:breakthroughs:{year + 1}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="« К графику",
            callback_data=f"chart:nav:{year}-{month:02d}",
        )
    )
    builder.row(InlineKeyboardButton(text="« Меню", callback_data="menu:home"))
    return builder.as_markup()


def time_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« Отмена", callback_data="menu:home")]
        ]
    )
