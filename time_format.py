from __future__ import annotations

import datetime as dt
import re

from ui_branding import (
    CUSTOM_EMOJI_BREAKTHROUGH,
    CUSTOM_EMOJI_LOG,
    CUSTOM_EMOJI_REST,
    PLACEHOLDER_BREAKTHROUGH,
    PLACEHOLDER_LOG,
    PLACEHOLDER_REST,
    tg_emoji,
)

TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")

MAX_MINUTES_PER_DAY = 24 * 60

TIME_PROMPT_HEADER = (
    f"{tg_emoji(CUSTOM_EMOJI_LOG, PLACEHOLDER_LOG)}Введите время:\n"
    "Пример: <code>7:30</code>"
)

TIME_INPUT_HINT = "Пример: <code>7:30</code>"

REST_INPUT_HINT = (
    f"{tg_emoji(CUSTOM_EMOJI_REST, PLACEHOLDER_REST)} "
    "Или отправьте <b>отдых</b>"
)

MAX_BREAKTHROUGH_NOTE_LEN = 300

BREAKTHROUGH_INPUT_HINT = (
    f"{tg_emoji(CUSTOM_EMOJI_BREAKTHROUGH, PLACEHOLDER_BREAKTHROUGH)} "
    "Или отправьте <b>прорыв</b>"
)

BREAKTHROUGH_NOTE_PROMPT = (
    f"{tg_emoji(CUSTOM_EMOJI_BREAKTHROUGH, PLACEHOLDER_BREAKTHROUGH)} "
    "<b>Опишите свой прорыв</b> одним сообщением.\n"
    "Этот текст появится в списке прорывов.\n\n"
    f"До {MAX_BREAKTHROUGH_NOTE_LEN} символов."
)

REST_KEYWORD = "отдых"
BREAKTHROUGH_KEYWORD = "прорыв"

DATE_PATTERN = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
DATE_INPUT_HINT = "Формат: <b>ДД.ММ.ГГГГ</b>\nПример: <code>15.05.2026</code>"


def parse_rest_input(text: str) -> bool:
    return text.strip().casefold() == REST_KEYWORD.casefold()


def parse_breakthrough_input(text: str) -> bool:
    return text.strip().casefold() == BREAKTHROUGH_KEYWORD.casefold()


def parse_time_input(text: str) -> tuple[int, int] | None:
    """Разбирает строку ЧЧ:ММ. Возвращает (часы, минуты) или None."""
    match = TIME_PATTERN.match(text.strip())
    if not match:
        return None

    hours, minutes = int(match.group(1)), int(match.group(2))
    if minutes >= 60:
        return None
    if hours == 0 and minutes == 0:
        return None
    if hours * 60 + minutes > MAX_MINUTES_PER_DAY:
        return None
    return hours, minutes


def duration_to_hours(hours: int, minutes: int) -> float:
    return hours + minutes / 60


def format_duration(hours: float) -> str:
    """Человекочитаемый вид: 2ч 30м."""
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    if h and m:
        return f"{h}ч {m}м"
    if h:
        return f"{h}ч"
    return f"{m}м"


def parse_date_input(text: str) -> dt.date | None:
    match = DATE_PATTERN.match(text.strip())
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def format_duration_clock(hours: float) -> str:
    """Вид ЧЧ:ММ для подсказок."""
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    return f"{h}:{m:02d}"
