"""Apple-style team statistics dashboard for Telegram."""
from __future__ import annotations

import asyncio
import datetime as dt

from database import (
    DayEntry,
    fill_missed_days_for_month,
    get_display_name,
    get_month_entries,
    get_registered_users,
)
from keyboards import MONTH_NAMES
from ui_branding import CUSTOM_EMOJI_PROGRESS, PLACEHOLDER_PROGRESS, tg_emoji

from dashboard.metrics import MetricsCalculator
from dashboard.renderer import DashboardRenderer
from dashboard.theme import Theme


async def _load_users_month_data(
    year: int, month: int
) -> list[tuple[str, dict[dt.date, DayEntry]]]:
    result: list[tuple[str, dict[dt.date, DayEntry]]] = []
    for user_id, name in await get_registered_users():
        display = await get_display_name(user_id) or name
        await fill_missed_days_for_month(user_id, display, year, month)
        entries = await get_month_entries(user_id, year, month)
        result.append((display, entries))
    return result


def _render_dashboard_png(
    users_data: list[tuple[str, dict[dt.date, DayEntry]]],
    year: int,
    month: int,
) -> bytes:
    theme = Theme()
    series: list[tuple[str, str, dict[dt.date, DayEntry]]] = []
    for idx, (name, entries) in enumerate(users_data):
        color = theme.user_colors[idx % len(theme.user_colors)]
        series.append((name, color, entries))
    metrics = MetricsCalculator.compute(series, year, month)
    return DashboardRenderer(theme).render(metrics)


async def build_team_dashboard(year: int, month: int) -> tuple[bytes, str]:
    users_data = await _load_users_month_data(year, month)
    if not users_data:
        raise RuntimeError("Нет зарегистрированных участников")

    png = await asyncio.to_thread(_render_dashboard_png, users_data, year, month)
    caption = (
        f"{tg_emoji(CUSTOM_EMOJI_PROGRESS, PLACEHOLDER_PROGRESS)} "
        f"<b>Общий прогресс</b> · {MONTH_NAMES[month]} {year}"
    )
    return png, caption
