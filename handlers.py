from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Message, User

from charts import build_breakthrough_year_calendar, build_team_progress_chart, chart_photo
from context import get_screen, set_screen
from database import (
    DayEntry,
    fill_all_missed_days,
    get_entry,
    get_registered_users,
    register_user,
    upsert_entry,
)
from keyboards import (
    breakthrough_calendar_keyboard,
    chart_nav_keyboard,
    main_menu_keyboard,
    time_prompt_keyboard,
)
from texts import format_user_stats
from time_format import (
    BREAKTHROUGH_INPUT_HINT,
    MAX_MINUTES_PER_DAY,
    REST_INPUT_HINT,
    TIME_INPUT_HINT,
    duration_to_hours,
    format_duration,
    format_duration_clock,
    parse_breakthrough_input,
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

_MESSAGE_NOT_MODIFIED = "message is not modified"

CHART_LOADING_TEXT = "📊 <b>График строится…</b> ⏳"
BREAKTHROUGH_LOADING_TEXT = "⭐ <b>Календарь прорывов строится…</b> ⏳"


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


async def safe_edit_text(
    message: Message,
    text: str,
    *,
    reply_markup=None,
) -> None:
    """Редактирует сообщение; повтор с тем же текстом не вызывает ошибку."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        msg = (exc.message or "").lower()
        if _MESSAGE_NOT_MODIFIED not in msg:
            raise


async def delete_message_safe(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


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
    loading = await message.answer(CHART_LOADING_TEXT)
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        png, caption = await build_team_progress_chart(year, month)
        await message.answer_photo(
            chart_photo(png),
            caption=caption,
            reply_markup=chart_nav_keyboard(year, month),
        )
    finally:
        await delete_message_safe(loading)


async def send_breakthrough_calendar(
    message: Message, year: int, month: int
) -> None:
    loading = await message.answer(BREAKTHROUGH_LOADING_TEXT)
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        png, caption = await build_breakthrough_year_calendar(year)
        await message.answer_photo(
            chart_photo(png, "breakthroughs.png"),
            caption=caption,
            reply_markup=breakthrough_calendar_keyboard(year, month),
        )
    finally:
        await delete_message_safe(loading)


async def send_full_statistics(message: Message, user_id: int) -> None:
    today = today_local()
    set_screen(user_id, "stats", chart_year=today.year, chart_month=today.month)

    await message.answer(await build_team_summary())
    await send_team_chart(message, today.year, today.month)


def _log_input_hints() -> str:
    return f"{TIME_INPUT_HINT}\n\n{REST_INPUT_HINT}\n{BREAKTHROUGH_INPUT_HINT}"


def time_prompt_text(today: dt.date, existing: DayEntry | None = None) -> str:
    date_label = today.strftime("%d.%m.%Y")
    text = (
        f"📅 Сегодня: <b>{date_label}</b>\n\n"
        f"Введите время продуктивной работы за день:\n{TIME_INPUT_HINT}\n\n"
        f"{REST_INPUT_HINT}\n"
        f"{BREAKTHROUGH_INPUT_HINT}\n\n"
        "Повторный ввод за тот же день <b>суммируется</b> с уже записанным временем."
    )
    if existing is not None:
        if existing.is_rest:
            text += (
                "\n\nСейчас: <b>день отдыха</b> — можно изменить "
                "(время, «отдых» или «прорыв»). Ввод времени заменит отметку отдыха."
            )
        elif existing.is_breakthrough:
            if existing.hours > 0:
                text += (
                    f"\n\nСейчас: <b>день прорыва</b> ⭐ · "
                    f"<b>{format_duration(existing.hours)}</b> "
                    f"(<code>{format_duration_clock(existing.hours)}</code>). "
                    "Новое время будет <b>прибавлено</b> к этой сумме."
                )
            else:
                text += (
                    "\n\nСейчас: <b>день прорыва</b> ⭐ — можно добавить время, "
                    "«прорыв» или «отдых»."
                )
        elif existing.hours > 0:
            text += (
                f"\n\nСейчас записано: <b>{format_duration(existing.hours)}</b> "
                f"(<code>{format_duration_clock(existing.hours)}</code>). "
                "Новое время будет <b>прибавлено</b> к этой сумме."
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
        await safe_edit_text(target.message, text, reply_markup=markup)


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
        await upsert_entry(
            user_id, today, 0.0, name, is_rest=True, is_breakthrough=False
        )
        await state.clear()
        set_screen(user_id, "menu")
        await message.answer(
            f"✅ Готово! {today.strftime('%d.%m.%Y')}: <b>день отдыха</b>."
        )
        await send_team_chart(message, today.year, today.month)
        return

    if parse_breakthrough_input(text):
        existing = await get_entry(user_id, today)
        hours = existing.hours if existing and existing.hours > 0 else 0.0
        await upsert_entry(
            user_id, today, hours, name, is_rest=False, is_breakthrough=True
        )
        await state.clear()
        set_screen(user_id, "menu")
        if hours > 0:
            result = (
                f"✅ Готово! {today.strftime('%d.%m.%Y')}: "
                f"<b>день прорыва</b> ⭐ · <b>{format_duration(hours)}</b>"
            )
        else:
            result = (
                f"✅ Готово! {today.strftime('%d.%m.%Y')}: <b>день прорыва</b> ⭐"
            )
        await message.answer(result)
        await send_team_chart(message, today.year, today.month)
        return

    parsed = parse_time_input(text)
    if parsed is None:
        await message.answer(
            f"Не удалось разобрать время.\n\n{_log_input_hints()}",
            reply_markup=time_prompt_keyboard(),
        )
        return

    hours_int, minutes = parsed
    added_hours = duration_to_hours(hours_int, minutes)

    existing = await get_entry(user_id, today)
    if existing is not None and not existing.is_rest and existing.hours > 0:
        total_hours = existing.hours + added_hours
    else:
        total_hours = added_hours

    if round(total_hours * 60) > MAX_MINUTES_PER_DAY:
        await message.answer(
            f"Сумма за день не может превышать 24 часа.\n\n{_log_input_hints()}",
            reply_markup=time_prompt_keyboard(),
        )
        return

    keep_breakthrough = bool(existing and existing.is_breakthrough)
    await upsert_entry(
        user_id,
        today,
        total_hours,
        name,
        is_rest=False,
        is_breakthrough=keep_breakthrough,
    )
    await state.clear()
    set_screen(user_id, "menu")

    if existing is not None and not existing.is_rest and existing.hours > 0:
        result_text = (
            f"✅ Готово! {today.strftime('%d.%m.%Y')}: "
            f"добавлено <b>{format_duration(added_hours)}</b>, "
            f"всего <b>{format_duration(total_hours)}</b> продуктивного времени."
        )
        if keep_breakthrough:
            result_text += " ⭐"
    else:
        result_text = (
            f"✅ Готово! {today.strftime('%d.%m.%Y')}: "
            f"<b>{format_duration(total_hours)}</b> продуктивного времени."
        )
        if keep_breakthrough:
            result_text += " ⭐"

    await message.answer(result_text)
    await send_team_chart(message, today.year, today.month)


@router.callback_query(F.data == "menu:stats")
async def menu_stats(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "📊 Строим статистику…")
    user_id = await ensure_user_callback(callback)
    if user_id is None:
        return
    if callback.message:
        await send_full_statistics(callback.message, user_id)


@router.callback_query(F.data.startswith("chart:breakthroughs:"))
async def chart_breakthroughs(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "⭐ Строим календарь…")
    viewer_id = await ensure_user_callback(callback)
    if viewer_id is None:
        return

    year = int(callback.data.split(":")[-1])
    ctx = get_screen(viewer_id)
    month = ctx.get("chart_month", today_local().month)

    set_screen(viewer_id, "stats", chart_year=year, chart_month=month)

    if callback.message:
        await send_breakthrough_calendar(callback.message, year, month)


@router.callback_query(F.data.startswith("chart:nav:"))
async def chart_nav(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "📊 Строим график…")
    viewer_id = await ensure_user_callback(callback)
    if viewer_id is None:
        return

    ym = callback.data.split(":")[-1]
    year, month = map(int, ym.split("-"))

    set_screen(viewer_id, "stats", chart_year=year, chart_month=month)

    if callback.message:
        await send_team_chart(callback.message, year, month)


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
