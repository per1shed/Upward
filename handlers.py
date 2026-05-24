from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User

from charts import build_team_progress_chart, chart_photo
from context import get_screen, set_screen
from database import (
    DayEntry,
    fill_all_missed_days,
    get_entry,
    get_registered_users,
    register_user,
    upsert_entry,
)
from keyboards import chart_nav_keyboard, main_menu_keyboard, time_prompt_keyboard
from texts import format_user_stats
from time_format import (
    REST_INPUT_HINT,
    TIME_INPUT_HINT,
    duration_to_hours,
    format_duration,
    format_duration_clock,
    parse_rest_input,
    parse_time_input,
)
from timezone_utils import today_local

router = Router()

WELCOME_TEXT = (
    "Привет! Это бот для отслеживания продуктивности за день.\n\n"
    "<b>✅отметить</b> — записать время за сегодня (ЧЧ:ММ)\n"
    "<b>📊 Статистика</b> — ваши показатели, общий прогресс и график"
)

UNEXPECTED_TEXT_MSG = (
    "Сейчас бот не ждёт текстового сообщения.\n"
    "Используйте кнопки под сообщениями или команду /start."
)


class LogTime(StatesGroup):
    waiting_time = State()


_EXPIRED_CALLBACK_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
)


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    """Снимает «часики»; устаревшие callback после перезапуска бота не падают."""
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        msg = (exc.message or "").lower()
        if not any(marker in msg for marker in _EXPIRED_CALLBACK_MARKERS):
            raise


def display_name_from_user(user: User) -> str:
    if user.username:
        return f"@{user.username}"
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(p for p in parts if p).strip() or f"ID {user.id}"


async def ensure_user(message: Message) -> int | None:
    if not message.from_user:
        return None
    name = display_name_from_user(message.from_user)
    await register_user(message.from_user.id, name)
    await fill_all_missed_days()
    return message.from_user.id


async def ensure_user_callback(callback: CallbackQuery) -> int | None:
    if not callback.from_user:
        return None
    name = display_name_from_user(callback.from_user)
    await register_user(callback.from_user.id, name)
    await fill_all_missed_days()
    return callback.from_user.id


async def send_team_chart(message: Message, year: int, month: int) -> None:
    png, caption = await build_team_progress_chart(year, month)
    await message.answer_photo(
        chart_photo(png),
        caption=caption,
        reply_markup=chart_nav_keyboard(year, month),
    )


async def send_full_statistics(message: Message, user_id: int) -> None:
    today = today_local()
    set_screen(user_id, "stats", chart_year=today.year, chart_month=today.month)

    await message.answer(await format_user_stats(user_id, heading="Ваша статистика"))
    await message.answer(await build_team_summary())
    await send_team_chart(message, today.year, today.month)


def time_prompt_text(today: dt.date, existing: DayEntry | None = None) -> str:
    date_label = today.strftime("%d.%m.%Y")
    text = (
        f"📅 Сегодня: <b>{date_label}</b>\n\n"
        f"Введите время продуктивной работы за день:\n{TIME_INPUT_HINT}\n\n"
        f"{REST_INPUT_HINT}"
    )
    if existing is not None:
        if existing.is_rest:
            text += (
                "\n\nСейчас: <b>день отдыха</b> — можно изменить "
                "(время или снова «отдых»)."
            )
        elif existing.hours > 0:
            text += (
                f"\n\nСейчас записано: <b>{format_duration(existing.hours)}</b> "
                f"(<code>{format_duration_clock(existing.hours)}</code>) "
                "— можно обновить."
            )
    return text


async def show_main_menu(message: Message) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


async def restore_screen(message: Message, state: FSMContext, user_id: int) -> None:
    ctx = get_screen(user_id)
    screen = ctx.get("screen", "menu")

    if screen == "menu":
        await show_main_menu(message)
        return

    if screen == "stats":
        await send_full_statistics(message, user_id)
        return

    if screen == "log":
        await ask_time_for_today(message, state, user_id)
        return

    await show_main_menu(message)


async def ask_time_for_today(
    target: Message | CallbackQuery,
    state: FSMContext,
    user_id: int,
) -> None:
    set_screen(user_id, "log")
    today = today_local()
    existing = await get_entry(user_id, today)
    await state.update_data(entry_date=today.isoformat())
    await state.set_state(LogTime.waiting_time)
    text = time_prompt_text(today, existing)
    markup = time_prompt_keyboard()

    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    elif target.message:
        await target.message.edit_text(text, reply_markup=markup)


async def build_team_summary() -> str:
    users = await get_registered_users()
    if not users:
        return (
            "<b>Общий прогресс</b>\n\n"
            "Пока никто не нажимал /start. Отправьте /start, чтобы появиться в списке."
        )

    blocks: list[str] = ["<b>Общий прогресс</b>\n"]
    for uid, name in users:
        blocks.append(await format_user_stats(uid))
        blocks.append("")
    return "\n".join(blocks).strip()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    user_id = await ensure_user(message)
    if user_id is None:
        return
    await state.clear()
    set_screen(user_id, "menu")
    await show_main_menu(message)


@router.message(Command("log"))
async def cmd_log(message: Message, state: FSMContext) -> None:
    user_id = await ensure_user(message)
    if user_id is None:
        return
    await state.clear()
    await ask_time_for_today(message, state, user_id)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    user_id = await ensure_user(message)
    if user_id is None:
        return
    await send_full_statistics(message, user_id)


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    user_id = await ensure_user_callback(callback)
    if user_id is None:
        return
    await state.clear()
    set_screen(user_id, "menu")
    if callback.message:
        await show_main_menu(callback.message)


@router.callback_query(F.data == "menu:log")
async def menu_log(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    user_id = await ensure_user_callback(callback)
    if user_id is None:
        return
    await state.clear()
    if callback.message:
        await ask_time_for_today(callback, state, user_id)


@router.message(LogTime.waiting_time)
async def log_time_input(message: Message, state: FSMContext) -> None:
    user_id = await ensure_user(message)
    if user_id is None:
        return

    today = today_local()
    data = await state.get_data()
    entry_date = dt.date.fromisoformat(data.get("entry_date", today.isoformat()))
    if entry_date != today:
        await state.clear()
        await message.answer(
            "Отметить можно только сегодня. Нажмите «✅отметить» снова.",
            reply_markup=main_menu_keyboard(),
        )
        return

    text = message.text or ""
    name = display_name_from_user(message.from_user)

    if parse_rest_input(text):
        await upsert_entry(user_id, today, 0.0, name, is_rest=True)
        await state.clear()
        set_screen(user_id, "menu")
        await message.answer(
            f"✅ Готово! {today.strftime('%d.%m.%Y')}: <b>день отдыха</b>."
        )
        await send_team_chart(message, today.year, today.month)
        return

    parsed = parse_time_input(text)
    if parsed is None:
        await message.answer(
            f"Не удалось разобрать время.\n\n{TIME_INPUT_HINT}\n\n{REST_INPUT_HINT}",
            reply_markup=time_prompt_keyboard(),
        )
        return

    hours_int, minutes = parsed
    hours = duration_to_hours(hours_int, minutes)

    await upsert_entry(user_id, today, hours, name, is_rest=False)
    await state.clear()
    set_screen(user_id, "menu")

    await message.answer(
        f"✅ Готово! {today.strftime('%d.%m.%Y')}: "
        f"<b>{format_duration(hours)}</b> продуктивного времени."
    )
    await send_team_chart(message, today.year, today.month)


@router.callback_query(F.data == "menu:stats")
async def menu_stats(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    user_id = await ensure_user_callback(callback)
    if user_id is None:
        return
    if callback.message:
        await send_full_statistics(callback.message, user_id)


@router.callback_query(F.data.startswith("chart:nav:"))
async def chart_nav(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    viewer_id = await ensure_user_callback(callback)
    if viewer_id is None:
        return

    ym = callback.data.split(":")[-1]
    year, month = map(int, ym.split("-"))

    set_screen(viewer_id, "stats", chart_year=year, chart_month=month)

    if callback.message:
        png, caption = await build_team_progress_chart(year, month)
        await callback.message.answer_photo(
            chart_photo(png),
            caption=caption,
            reply_markup=chart_nav_keyboard(year, month),
        )


@router.message(F.text)
async def unexpected_text(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    if message.text.startswith("/"):
        return

    if await state.get_state() == LogTime.waiting_time:
        return

    user_id = await ensure_user(message)
    if user_id is None:
        return

    await message.answer(UNEXPECTED_TEXT_MSG)
    await restore_screen(message, state, user_id)
