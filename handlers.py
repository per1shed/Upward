from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, FSInputFile, Message, User

from charts import build_team_progress_chart, chart_photo
from context import get_screen, set_screen
from database import (
    DayEntry,
    fill_all_missed_days,
    get_entry,
    get_registered_users,
    register_user,
    set_breakthrough_note,
    upsert_entry,
)
from keyboards import (
    breakthrough_calendar_keyboard,
    cancel_keyboard,
    chart_nav_keyboard,
    main_menu_keyboard,
    time_prompt_keyboard,
)
from texts import format_breakthroughs_list, format_user_stats
from time_format import (
    BREAKTHROUGH_INPUT_HINT,
    BREAKTHROUGH_NOTE_PROMPT,
    MAX_BREAKTHROUGH_NOTE_LEN,
    MAX_MINUTES_PER_DAY,
    REST_INPUT_HINT,
    TIME_PROMPT_HEADER,
    duration_to_hours,
    format_duration,
    format_duration_clock,
    parse_breakthrough_input,
    parse_rest_input,
    parse_time_input,
)
from timezone_utils import today_local
from ui_branding import (
    CUSTOM_EMOJI_BREAKTHROUGH,
    CUSTOM_EMOJI_PROGRESS,
    PLACEHOLDER_BREAKTHROUGH,
    PLACEHOLDER_PROGRESS,
    WELCOME_PHOTO_PATH,
    format_breakthrough_done_message,
    format_rest_done_message,
    format_time_done_message,
    mention_log_button,
    tg_emoji,
)
from ui_keyboard import (
    answer_done,
    answer_photo_tracked,
    answer_tracked,
    edit_text_tracked,
)

router = Router()

UNEXPECTED_TEXT_MSG = (
    "Сейчас бот не ждёт текстового сообщения.\n"
    "Используйте кнопки под сообщениями или команду /start."
)


class LogTime(StatesGroup):
    waiting_time = State()
    waiting_breakthrough_note = State()


_EXPIRED_CALLBACK_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
)

CHART_LOADING_TEXT = "📊 <b>График строится…</b> ⏳"


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
) -> bool:
    """Редактирует текст. False, если сообщение нельзя править как текст."""
    return await edit_text_tracked(message, text, reply_markup=reply_markup)

def _message_is_plain_text(message: Message) -> bool:
    """True только для обычных текстовых сообщений (не фото/медиа)."""
    return bool(message.text) and not (
        message.photo
        or message.video
        or message.document
        or message.animation
        or message.sticker
    )

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
    loading = await answer_tracked(message, CHART_LOADING_TEXT)
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        png, caption = await build_team_progress_chart(year, month)
        await answer_photo_tracked(
            message,
            chart_photo(png),
            caption=caption,
            reply_markup=chart_nav_keyboard(year, month),
        )
    finally:
        await delete_message_safe(loading)


async def send_breakthrough_list(
    message: Message, year: int, month: int
) -> None:
    text = await format_breakthroughs_list(year)
    await answer_tracked(
        message,
        text,
        reply_markup=breakthrough_calendar_keyboard(year, month),
    )


async def send_full_statistics(message: Message, user_id: int) -> None:
    today = today_local()
    set_screen(user_id, "stats", chart_year=today.year, chart_month=today.month)

    await answer_tracked(message, await build_team_summary())
    await send_team_chart(message, today.year, today.month)


def _log_input_hints() -> str:
    return f"{TIME_PROMPT_HEADER}\n\n{REST_INPUT_HINT}\n{BREAKTHROUGH_INPUT_HINT}"


def time_prompt_text(today: dt.date, existing: DayEntry | None = None) -> str:
    text = (
        f"{TIME_PROMPT_HEADER}\n\n"
        f"{REST_INPUT_HINT}\n"
        f"{BREAKTHROUGH_INPUT_HINT}"
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
    await answer_photo_tracked(
        message,
        FSInputFile(WELCOME_PHOTO_PATH),
        reply_markup=main_menu_keyboard(),
    )


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

    if screen == "log_breakthrough":
        await state.set_state(LogTime.waiting_breakthrough_note)
        today = today_local()
        data = await state.get_data()
        if not data.get("entry_date"):
            await state.update_data(entry_date=today.isoformat())
        await answer_tracked(
            message,
            BREAKTHROUGH_NOTE_PROMPT,
            reply_markup=cancel_keyboard(),
        )
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
        await answer_tracked(target, text, reply_markup=markup)
    elif target.message:
        msg = target.message
        if _message_is_plain_text(msg):
            edited = await safe_edit_text(msg, text, reply_markup=markup)
            if edited:
                return
        await answer_tracked(msg, text, reply_markup=markup)


async def build_team_summary() -> str:
    title = (
        f"{tg_emoji(CUSTOM_EMOJI_PROGRESS, PLACEHOLDER_PROGRESS)} "
        "<b>Общий прогресс</b>"
    )
    users = await get_registered_users()
    if not users:
        return (
            f"{title}\n\n"
            "Пока никто не нажимал /start. Отправьте /start, чтобы появиться в списке."
        )

    blocks: list[str] = [f"{title}\n"]
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
    if callback.message:
        await ask_time_for_today(callback, state, user_id)


@router.message(LogTime.waiting_time, F.text)
async def log_time_input(message: Message, state: FSMContext) -> None:
    user_id = await ensure_user(message)
    if user_id is None:
        return

    today = today_local()
    data = await state.get_data()
    entry_date = dt.date.fromisoformat(data.get("entry_date", today.isoformat()))
    if entry_date != today:
        await state.clear()
        await answer_tracked(
            message,
            "Отметить можно только сегодня. Нажмите " + mention_log_button() + " снова.",
            reply_markup=main_menu_keyboard(),
        )
        return

    text = message.text or ""
    name = display_name_from_user(message.from_user)

    if parse_rest_input(text):
        await _mark_rest_day(message, state, user_id, today, name)
        return

    if parse_breakthrough_input(text):
        await _start_breakthrough(message, state, user_id, today, name)
        return

    parsed = parse_time_input(text)
    if parsed is None:
        await answer_tracked(
            message,
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
        await answer_tracked(
            message,
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
        keep_existing_note=keep_breakthrough,
    )
    await state.clear()
    set_screen(user_id, "menu")

    result_text = format_time_done_message(added_hours, total_hours)
    if keep_breakthrough:
        result_text += " " + tg_emoji(
            CUSTOM_EMOJI_BREAKTHROUGH, PLACEHOLDER_BREAKTHROUGH
        )

    await answer_done(message, result_text)
    await send_team_chart(message, today.year, today.month)


async def _mark_rest_day(
    message: Message,
    state: FSMContext,
    user_id: int,
    today: dt.date,
    name: str,
) -> None:
    await upsert_entry(
        user_id, today, 0.0, name, is_rest=True, is_breakthrough=False
    )
    await state.clear()
    set_screen(user_id, "menu")
    await answer_done(message, format_rest_done_message())
    await send_team_chart(message, today.year, today.month)


async def _start_breakthrough(
    message: Message,
    state: FSMContext,
    user_id: int,
    today: dt.date,
    name: str,
) -> None:
    existing = await get_entry(user_id, today)
    hours = existing.hours if existing and existing.hours > 0 else 0.0
    await upsert_entry(
        user_id,
        today,
        hours,
        name,
        is_rest=False,
        is_breakthrough=True,
        breakthrough_note="",
    )
    await state.update_data(entry_date=today.isoformat())
    await state.set_state(LogTime.waiting_breakthrough_note)
    set_screen(user_id, "log_breakthrough")
    await answer_tracked(
        message,
        BREAKTHROUGH_NOTE_PROMPT,
        reply_markup=cancel_keyboard(),
    )


@router.callback_query(LogTime.waiting_time, F.data == "log:rest")
async def log_rest_button(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    user_id = await ensure_user_callback(callback)
    if user_id is None or not callback.message or not callback.from_user:
        return

    today = today_local()
    data = await state.get_data()
    entry_date = dt.date.fromisoformat(data.get("entry_date", today.isoformat()))
    if entry_date != today:
        await state.clear()
        await answer_tracked(
            callback.message,
            "Отметить можно только сегодня. Нажмите " + mention_log_button() + " снова.",
            reply_markup=main_menu_keyboard(),
        )
        return

    name = display_name_from_user(callback.from_user)
    await _mark_rest_day(callback.message, state, user_id, today, name)


@router.callback_query(LogTime.waiting_time, F.data == "log:breakthrough")
async def log_breakthrough_button(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    user_id = await ensure_user_callback(callback)
    if user_id is None or not callback.message or not callback.from_user:
        return

    today = today_local()
    data = await state.get_data()
    entry_date = dt.date.fromisoformat(data.get("entry_date", today.isoformat()))
    if entry_date != today:
        await state.clear()
        await answer_tracked(
            callback.message,
            "Отметить можно только сегодня. Нажмите " + mention_log_button() + " снова.",
            reply_markup=main_menu_keyboard(),
        )
        return

    name = display_name_from_user(callback.from_user)
    await _start_breakthrough(callback.message, state, user_id, today, name)


@router.message(LogTime.waiting_breakthrough_note, F.text)
async def breakthrough_note_input(message: Message, state: FSMContext) -> None:
    user_id = await ensure_user(message)
    if user_id is None:
        return

    today = today_local()
    data = await state.get_data()
    entry_date = dt.date.fromisoformat(data.get("entry_date", today.isoformat()))
    if entry_date != today:
        await state.clear()
        await answer_tracked(
            message,
            "Описать прорыв можно только за сегодня. Нажмите " + mention_log_button() + " снова.",
            reply_markup=main_menu_keyboard(),
        )
        return

    note = (message.text or "").strip()
    if not note:
        await answer_tracked(
            message,
            "Описание не должно быть пустым.\n\n" + BREAKTHROUGH_NOTE_PROMPT,
            reply_markup=cancel_keyboard(),
        )
        return
    if len(note) > MAX_BREAKTHROUGH_NOTE_LEN:
        await answer_tracked(
            message,
            f"Слишком длинно: максимум {MAX_BREAKTHROUGH_NOTE_LEN} символов.\n\n"
            + BREAKTHROUGH_NOTE_PROMPT,
            reply_markup=cancel_keyboard(),
        )
        return

    saved = await set_breakthrough_note(user_id, today, note)
    await state.clear()
    set_screen(user_id, "menu")

    if not saved:
        await answer_tracked(
            message,
            "Не удалось сохранить описание: день прорыва не найден.\n"
            "Отметьте прорыв снова через " + mention_log_button() + ".",
            reply_markup=main_menu_keyboard(),
        )
        return

    entry = await get_entry(user_id, today)
    hours = entry.hours if entry else 0.0
    await answer_done(message, format_breakthrough_done_message(hours, note))
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
    await safe_callback_answer(callback)
    viewer_id = await ensure_user_callback(callback)
    if viewer_id is None:
        return

    year = int(callback.data.split(":")[-1])
    ctx = get_screen(viewer_id)
    month = ctx.get("chart_month", today_local().month)

    set_screen(viewer_id, "stats", chart_year=year, chart_month=month)

    if callback.message:
        await send_breakthrough_list(callback.message, year, month)


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


@router.message(F.text, StateFilter(None))
async def unexpected_text(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    if message.text.startswith("/"):
        return

    user_id = await ensure_user(message)
    if user_id is None:
        return

    # FSM мог сброситься, но экран всё ещё «ввод времени» (Отметить / Отметить снова)
    if get_screen(user_id).get("screen") == "log":
        today = today_local()
        await state.set_state(LogTime.waiting_time)
        data = await state.get_data()
        if not data.get("entry_date"):
            await state.update_data(entry_date=today.isoformat())
        await log_time_input(message, state)
        return

    if get_screen(user_id).get("screen") == "log_breakthrough":
        today = today_local()
        await state.set_state(LogTime.waiting_breakthrough_note)
        data = await state.get_data()
        if not data.get("entry_date"):
            await state.update_data(entry_date=today.isoformat())
        await breakthrough_note_input(message, state)
        return

    await answer_tracked(message, UNEXPECTED_TEXT_MSG)
    await restore_screen(message, state, user_id)
