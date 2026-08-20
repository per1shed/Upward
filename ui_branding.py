"""UI constants: welcome photo and custom emoji stickers."""
from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
WELCOME_PHOTO_PATH = ASSETS_DIR / "welcome.png"

# Custom emoji from Telegram (Premium stickers)
CUSTOM_EMOJI_LOG = "5201691993775818138"  # отметить
CUSTOM_EMOJI_STATS = "5429651785352501917"  # статистика
CUSTOM_EMOJI_REST = "5267102644886853973"  # отдых
CUSTOM_EMOJI_BREAKTHROUGH = "5267500801240092311"  # прорыв
CUSTOM_EMOJI_PROGRESS = "5190806721286657692"  # общий прогресс

# Success marker before «Готово!» (🎯 — same as former dice sticker)
EMOJI_DONE = "\U0001f3af"

# UTF-16 placeholders matching the custom emoji entities
PLACEHOLDER_LOG = "\U0001f6eb"  # 🛫
PLACEHOLDER_STATS = "\u2197\ufe0f"  # ↗️
PLACEHOLDER_REST = "\u2764\ufe0f"  # ❤️
PLACEHOLDER_BREAKTHROUGH = "\u2b50"  # ⭐
PLACEHOLDER_PROGRESS = "\U0001f4ca"  # 📊

BTN_LOG_TEXT = "Отметить"
BTN_STATS_TEXT = "Статистика"
BTN_REST_TEXT = "Отдых"
BTN_BREAKTHROUGH_TEXT = "Прорыв"
BTN_BREAKTHROUGHS_TEXT = "Прорывы"


def tg_emoji(emoji_id: str, placeholder: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{placeholder}</tg-emoji>'


def mention_log_button() -> str:
    """Text reference to the log action (for tips / errors)."""
    return f"«{PLACEHOLDER_LOG}{BTN_LOG_TEXT}»"


def format_time_done_message(added_hours: float, total_hours: float) -> str:
    """Single success message after logging time."""
    from time_format import format_duration

    return (
        f"{EMOJI_DONE}Готово!\n"
        f"{tg_emoji(CUSTOM_EMOJI_LOG, PLACEHOLDER_LOG)} "
        f"Добавлено: <b>{format_duration(added_hours)}</b>\n"
        f"{tg_emoji(CUSTOM_EMOJI_STATS, PLACEHOLDER_STATS)} "
        f"Всего: <b>{format_duration(total_hours)}</b> продуктивного времени."
    )


def format_rest_done_message() -> str:
    return (
        f"{EMOJI_DONE}Готово!\n"
        f"{tg_emoji(CUSTOM_EMOJI_REST, PLACEHOLDER_REST)} <b>день отдыха</b>"
    )


def format_breakthrough_done_message(hours: float, note: str) -> str:
    from time_format import format_duration
    from html import escape

    note_safe = escape(note)
    star = tg_emoji(CUSTOM_EMOJI_BREAKTHROUGH, PLACEHOLDER_BREAKTHROUGH)
    if hours > 0:
        return (
            f"{EMOJI_DONE}Готово!\n"
            f"{star} <b>день прорыва</b> · <b>{format_duration(hours)}</b>\n"
            f"Описание: <i>{note_safe}</i>"
        )
    return (
        f"{EMOJI_DONE}Готово!\n"
        f"{star} <b>день прорыва</b>\n"
        f"Описание: <i>{note_safe}</i>"
    )
