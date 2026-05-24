from __future__ import annotations

import asyncio
import calendar
import datetime as dt
import io
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from database import (
    DayEntry,
    fill_missed_days_for_month,
    get_display_name,
    get_month_entries,
    get_registered_users,
)
from keyboards import MONTH_NAMES
from time_format import format_duration, format_duration_clock

if TYPE_CHECKING:
    from aiogram.types import BufferedInputFile

USER_COLORS = ("#5B8DEF", "#E85D4E", "#3CB371", "#F4A460", "#9B59B6", "#1ABC9C")
EMPTY_COLOR = "#D8DEE9"
PRODUCTIVE_COLOR = "#5B8DEF"
HIGHLIGHT_COLOR = "#E85D4E"
# Мягкий шалфейно-мятный — ассоциация с отдыхом и восстановлением
REST_COLOR = "#73C6A8"
REST_DISPLAY_HOURS = 8.0


def _entry_for_day(
    entries: dict[dt.date, DayEntry], day: dt.date
) -> DayEntry:
    return entries.get(day, DayEntry(0.0, False))


def _bar_display_height(entry: DayEntry) -> float:
    if entry.is_rest:
        return REST_DISPLAY_HOURS
    return entry.hours


def _user_bar_color(base_color: str, entry: DayEntry) -> str | tuple:
    """Отдых — цвет восстановления; продуктивность — цвет участника; пустой день — бледный."""
    if entry.is_rest:
        return REST_COLOR
    if entry.hours > 0:
        return base_color
    return mcolors.to_rgba(base_color, alpha=0.22)


def _day_bar_color(
    entry: DayEntry,
    *,
    highlight: bool = False,
) -> str:
    if highlight:
        return HIGHLIGHT_COLOR
    if entry.is_rest:
        return REST_COLOR
    if entry.hours > 0:
        return PRODUCTIVE_COLOR
    return EMPTY_COLOR


def _render_single_chart(
    entries: dict[dt.date, DayEntry],
    title: str,
    year: int,
    month: int,
    highlight: dt.date | None,
) -> bytes:
    _, last_day = calendar.monthrange(year, month)
    all_days = [dt.date(year, month, day) for day in range(1, last_day + 1)]
    day_entries = [_entry_for_day(entries, day) for day in all_days]
    total_month = sum(e.hours for e in day_entries)
    values = [_bar_display_height(e) for e in day_entries]
    max_value = max(values) if values else 1.0

    fig, ax = plt.subplots(figsize=(max(12, last_day * 0.38), 5.5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    day_numbers = list(range(1, last_day + 1))
    colors = [
        _day_bar_color(
            day_entries[i],
            highlight=bool(highlight and day == highlight),
        )
        for i, day in enumerate(all_days)
    ]

    bars = ax.bar(day_numbers, values, color=colors, width=0.72, edgecolor="white")
    ax.set_xlabel("День месяца", fontsize=11)
    ax.set_ylabel("Время (часы)", fontsize=11)
    ax.set_xlim(0.4, last_day + 0.6)
    ax.set_xticks(day_numbers)
    ax.set_xticklabels(day_numbers, fontsize=8)
    ax.set_ylim(0, max(max_value * 1.3, REST_DISPLAY_HOURS * 1.08))
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    for bar, day, entry in zip(bars, all_days, day_entries):
        if entry.is_rest or entry.hours <= 0:
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            format_duration_clock(entry.hours),
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="#222222",
        )

    legend_handles = [
        Patch(facecolor=PRODUCTIVE_COLOR, edgecolor="white", label="продуктивность"),
        Patch(facecolor=REST_COLOR, edgecolor="white", label="отдых"),
        Patch(facecolor=EMPTY_COLOR, edgecolor="white", label="нет записи"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8, framealpha=0.9)

    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    month_total = (
        f"Итого за месяц: {format_duration(total_month)}"
        if total_month > 0
        else "Итого за месяц: 0ч"
    )
    fig.text(0.5, 0.02, month_total, ha="center", fontsize=10, color="#444444")

    buf = io.BytesIO()
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_team_chart(
    users_series: list[tuple[str, dict[dt.date, DayEntry]]],
    title: str,
    year: int,
    month: int,
) -> bytes:
    _, last_day = calendar.monthrange(year, month)
    all_days = [dt.date(year, month, day) for day in range(1, last_day + 1)]
    day_numbers = np.arange(1, last_day + 1)
    n_users = len(users_series)

    fig, ax = plt.subplots(figsize=(max(12, last_day * 0.42), 6))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    group_width = 0.82
    bar_width = group_width / max(n_users, 1)

    all_day_entries = [
        [_entry_for_day(entries, day) for day in all_days]
        for _name, entries in users_series
    ]
    max_value = 0.0

    for idx, (name, entries) in enumerate(users_series):
        day_entries = all_day_entries[idx]
        values = [_bar_display_height(e) for e in day_entries]
        max_value = max(max_value, max(values) if values else 0.0)
        offset = (idx - (n_users - 1) / 2) * bar_width
        x = day_numbers + offset
        base_color = USER_COLORS[idx % len(USER_COLORS)]

        bar_colors = [_user_bar_color(base_color, e) for e in day_entries]

        bars = ax.bar(
            x,
            values,
            width=bar_width * 0.92,
            color=bar_colors,
            edgecolor="white",
            linewidth=0.6,
        )

        for bar, entry in zip(bars, day_entries):
            if entry.is_rest or entry.hours <= 0:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                format_duration_clock(entry.hours),
                ha="center",
                va="bottom",
                fontsize=7,
                fontweight="bold",
                color="#222222",
            )

    ax.set_xlabel("День месяца", fontsize=11)
    ax.set_ylabel("Время (часы)", fontsize=11)
    ax.set_xlim(0.4, last_day + 0.6)
    ax.set_xticks(day_numbers)
    ax.set_xticklabels([str(d) for d in day_numbers], fontsize=8)
    y_top = max(max_value * 1.35, REST_DISPLAY_HOURS * 1.08)
    ax.set_ylim(0, y_top)
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    user_handles = [
        Patch(
            facecolor=USER_COLORS[idx % len(USER_COLORS)],
            edgecolor=USER_COLORS[idx % len(USER_COLORS)],
            label=name,
        )
        for idx, (name, _) in enumerate(users_series)
    ]
    rest_handle = Patch(facecolor=REST_COLOR, edgecolor=REST_COLOR, label="отдых")
    ax.legend(
        handles=user_handles + [rest_handle],
        loc="upper right",
        fontsize=9,
        framealpha=0.9,
    )
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

    totals = [
        f"{name}: {format_duration(sum(_entry_for_day(entries, d).hours for d in all_days))}"
        for name, entries in users_series
    ]
    fig.text(0.5, 0.02, " · ".join(totals), ha="center", fontsize=9, color="#444444")

    buf = io.BytesIO()
    plt.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


async def _load_users_month_data(
    year: int, month: int,
) -> list[tuple[int, str, dict[dt.date, DayEntry]]]:
    result: list[tuple[int, str, dict[dt.date, DayEntry]]] = []
    for user_id, name in await get_registered_users():
        display = await get_display_name(user_id) or name
        await fill_missed_days_for_month(user_id, display, year, month)
        entries = await get_month_entries(user_id, year, month)
        result.append((user_id, display, entries))
    return result


async def build_team_progress_chart(year: int, month: int) -> tuple[bytes, str]:
    users_data = await _load_users_month_data(year, month)
    if not users_data:
        raise RuntimeError("Нет зарегистрированных участников")

    users_series = [(name, entries) for _, name, entries in users_data]
    title = f"Общий прогресс — {MONTH_NAMES[month]} {year}"
    png = await asyncio.to_thread(
        _render_team_chart, users_series, title, year, month
    )
    caption = f"📊 <b>Общий график</b> · {MONTH_NAMES[month]} {year}"
    return png, caption


async def build_progress_chart(
    user_id: int,
    year: int,
    month: int,
    *,
    highlight: dt.date | None = None,
) -> tuple[bytes, str]:
    """Один участник — для обратной совместимости."""
    name = await get_display_name(user_id) or f"ID {user_id}"
    await fill_missed_days_for_month(user_id, name, year, month)
    entries = await get_month_entries(user_id, year, month)
    title = f"{name} — {MONTH_NAMES[month]} {year}"
    png = await asyncio.to_thread(
        _render_single_chart, entries, title, year, month, highlight
    )

    if highlight and highlight in entries:
        day_label = highlight.strftime("%d.%m.%Y")
        entry = entries[highlight]
        if entry.is_rest:
            day_info = "<b>день отдыха</b>"
        else:
            day_info = (
                f"<b>{format_duration(entry.hours)}</b> "
                f"(<code>{format_duration_clock(entry.hours)}</code>)"
            )
        caption = (
            f"📊 <b>{name}</b> · {MONTH_NAMES[month]} {year}\n"
            f"Отмечено {day_label}: {day_info}"
        )
    else:
        caption = f"📊 <b>{name}</b> · {MONTH_NAMES[month]} {year}"

    return png, caption


def chart_photo(png: bytes, filename: str = "progress.png") -> BufferedInputFile:
    from aiogram.types import BufferedInputFile

    return BufferedInputFile(png, filename=filename)
