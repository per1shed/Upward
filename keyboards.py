from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from access import PASHOK_ID
from ui_branding import (
    BTN_BREAKTHROUGH_TEXT,
    BTN_BREAKTHROUGHS_TEXT,
    BTN_LOG_TEXT,
    BTN_REST_TEXT,
    BTN_STATS_TEXT,
    CUSTOM_EMOJI_BREAKTHROUGH,
    CUSTOM_EMOJI_LOG,
    CUSTOM_EMOJI_REST,
    CUSTOM_EMOJI_STATS,
)

def _button(
    text: str,
    callback_data: str,
    *,
    user_id: int | None = None,
    icon: str | None = None,
    style: str | None = None,
) -> InlineKeyboardButton:
    if user_id == PASHOK_ID:
        if style is None:
            green = text == BTN_LOG_TEXT or text == f"{BTN_LOG_TEXT} снова"
            style = "success" if green else "primary"
        return InlineKeyboardButton(text=text, callback_data=callback_data, style=style)
    if icon:
        return InlineKeyboardButton(
            text=text,
            callback_data=callback_data,
            icon_custom_emoji_id=icon,
        )
    return InlineKeyboardButton(text=text, callback_data=callback_data)


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


def main_menu_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(BTN_LOG_TEXT, "menu:log", user_id=user_id, icon=CUSTOM_EMOJI_LOG),
        _button(BTN_STATS_TEXT, "menu:stats", user_id=user_id, icon=CUSTOM_EMOJI_STATS),
    )
    if user_id == PASHOK_ID:
        builder.row(
            _button("Финансы", "p:fin", user_id=user_id),
            _button("Секундомер", "p:sw", user_id=user_id),
        )
    return builder.as_markup()


async def main_menu_markup(user_id: int | None = None) -> InlineKeyboardMarkup:
    return main_menu_keyboard(user_id)


def _month_row(prefix: str, year: int, month: int) -> list[InlineKeyboardButton]:
    from pavel import month_allowed, shift_month

    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)
    if not month_allowed(prev_year, prev_month):
        prev_year, prev_month = year, month
    if not month_allowed(next_year, next_month):
        next_year, next_month = year, month
    return [
        _button("←", f"{prefix}:{prev_year}-{prev_month:02d}", user_id=PASHOK_ID),
        _button(MONTH_NAMES[month], f"{prefix}:{year}-{month:02d}", user_id=PASHOK_ID),
        _button("→", f"{prefix}:{next_year}-{next_month:02d}", user_id=PASHOK_ID),
    ]


def finance_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(*_month_row("p:fin", year, month))
    builder.row(
        _button("Баланс", "p:fin:balance", user_id=PASHOK_ID),
        _button("Долги", "p:fin:debt", user_id=PASHOK_ID),
    )
    builder.row(_button("« Меню", "menu:home", user_id=PASHOK_ID))
    return builder.as_markup()


def state_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(*_month_row("p:state", year, month))
    builder.row(_button("Отметить состояние", "p:state:ask", user_id=PASHOK_ID))
    builder.row(_button("« Меню", "menu:home", user_id=PASHOK_ID))
    return builder.as_markup()


def state_kind_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_button("Физическое", "p:state:kind:p", user_id=PASHOK_ID))
    builder.row(_button("Моральное", "p:state:kind:m", user_id=PASHOK_ID))
    builder.row(_button("« Назад", "p:state", user_id=PASHOK_ID))
    return builder.as_markup()


def state_score_keyboard(kind: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        *[
            _button(str(score), f"p:state:set:{kind}:{score}", user_id=PASHOK_ID)
            for score in range(1, 6)
        ]
    )
    builder.row(_button("« Назад", "p:state:ask", user_id=PASHOK_ID))
    return builder.as_markup()


def stopwatch_keyboard(status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "running":
        builder.row(
            _button("Пауза", "p:sw:pause", user_id=PASHOK_ID),
            _button("Круг", "p:sw:lap", user_id=PASHOK_ID),
        )
        builder.row(
            _button("Обновить", "p:sw:refresh", user_id=PASHOK_ID),
            _button("Сброс", "p:sw:reset", user_id=PASHOK_ID),
        )
    elif status == "paused":
        builder.row(_button("Продолжить", "p:sw:start", user_id=PASHOK_ID))
        builder.row(_button("Сброс", "p:sw:reset", user_id=PASHOK_ID))
    else:
        builder.row(_button("Старт", "p:sw:start", user_id=PASHOK_ID))
    builder.row(_button("« Меню", "menu:home", user_id=PASHOK_ID))
    return builder.as_markup()


def plan_keyboard(stored_mode: str) -> InlineKeyboardMarkup:
    from pavel import mode_label

    builder = InlineKeyboardBuilder()
    builder.row(_button(f"Расписание · {mode_label(stored_mode)}", "p:plan:mode", user_id=PASHOK_ID))
    builder.row(_button("« Меню", "menu:home", user_id=PASHOK_ID))
    return builder.as_markup()


def goal_keyboard(has_goal: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_goal:
        builder.row(_button("Снять цель", "p:goal:clear", user_id=PASHOK_ID))
    builder.row(_button("« Отмена", "menu:home", user_id=PASHOK_ID))
    return builder.as_markup()


def chart_nav_keyboard(year: int, month: int, user_id: int | None = None) -> InlineKeyboardMarkup:
    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month + 1 if month < 12 else 1
    next_year = year + 1 if month == 12 else year

    builder = InlineKeyboardBuilder()
    builder.row(
        _button("←", f"chart:nav:{prev_year}-{prev_month:02d}", user_id=user_id),
        _button(MONTH_NAMES[month], f"chart:nav:{year}-{month:02d}", user_id=user_id),
        _button("→", f"chart:nav:{next_year}-{next_month:02d}", user_id=user_id),
    )
    builder.row(
        _button(f"{BTN_LOG_TEXT} снова", "menu:log", user_id=user_id, icon=CUSTOM_EMOJI_LOG)
    )
    builder.row(
        _button("« Меню", "menu:home", user_id=user_id),
        _button(
            BTN_BREAKTHROUGHS_TEXT,
            f"chart:breakthroughs:{year}",
            user_id=user_id,
            icon=CUSTOM_EMOJI_BREAKTHROUGH,
        ),
    )
    return builder.as_markup()


def breakthrough_calendar_keyboard(
    year: int, month: int, user_id: int | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button("←", f"chart:breakthroughs:{year - 1}", user_id=user_id),
        _button(str(year), f"chart:breakthroughs:{year}", user_id=user_id),
        _button("→", f"chart:breakthroughs:{year + 1}", user_id=user_id),
    )
    builder.row(_button("« К графику", f"chart:nav:{year}-{month:02d}", user_id=user_id))
    builder.row(_button("« Меню", "menu:home", user_id=user_id))
    return builder.as_markup()


def time_prompt_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(BTN_REST_TEXT, "log:rest", user_id=user_id, icon=CUSTOM_EMOJI_REST),
                _button(
                    BTN_BREAKTHROUGH_TEXT,
                    "log:breakthrough",
                    user_id=user_id,
                    icon=CUSTOM_EMOJI_BREAKTHROUGH,
                ),
            ],
            [_button("« Отмена", "menu:home", user_id=user_id)],
        ]
    )


def cancel_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button("« Отмена", "menu:home", user_id=user_id)]]
    )
